# Feature Specification: Spec 005 — Agent Hardening (Production-Grade Resilience)

**Feature Branch**: `005-agent-hardening`

**Created**: 2026-06-03

**Updated**: 2026-06-03

**Status**: Draft

**Input**: Análise de gaps agênticos mapeados no `docs/AgendAI_Architecture_Roadmap.pdf` (V2.0)
e observações de produção na Fase 1 (Render). Baseado nos whitepapers *Prototype to Production*,
*Context Engineering: Sessions & Memory* e *Agentic Design Patterns* (Google Cloud, 2025).

---

## Why This Feature Exists

O AgendAI está em produção na Fase 1 (Render + GitHub Actions). A análise de gaps agênticos
identificou que, apesar de funcionar, o sistema não é production-grade em sete dimensões:
resiliência a falhas, persistência de sessão, identidade de usuário, segurança de conteúdo
(input e output), observabilidade, gerenciamento de contexto e memória de longo prazo. Cada
gap transforma um problema isolado em degradação visível ao usuário ou risco de segurança.

Esta spec endereça os 7 gaps em ordem de impacto × esforço.

---

## Gaps Mapeados (P1 → P7)

### P1 — Retry + Circuit Breaker

**Problema:** `llm_core.py`, `transcriber.py` e `api_client.py` não têm retry. Uma falha
transiente da OpenAI (`RateLimitError`, `APITimeoutError`) ou da API interna (cold start no
Render) encerra o run do grafo permanentemente. `tts.py` e `email_sender.py` já têm tenacity.

**Decisão técnica:** Ver [ADR-024](../../docs/adr/ADR-024-retry-resilience-strategy.md).

**Escopo:**
- `agent/agent/nodes/llm_core.py` — retry tenacity + circuit breaker pybreaker
- `agent/agent/nodes/transcriber.py` — retry tenacity
- `agent/agent/api_client.py` — retry tenacity (só `ConnectError`/`TimeoutException`, não 4xx)
- `api/src/db/connection.js` — async-retry no startup (5x, até 30s)
- `api/src/repositories/*.js` — p-retry em queries transientes

---

### P2 — Sessão persistente por usuário

**Problema:** `InMemoryCheckpointer` (ADR-014) reseta em restart. Conversas não sobrevivem a
redeploys. Cada restart do `langgraph-server` apaga o histórico de todos os threads.

**Decisão:** Migrar para `PostgresSaver` (Fase 1-2) ou Vertex AI Agent Engine Sessions (Fase 3).
Cada conversa ganha um `thread_id` por `user_id` e sobrevive a restarts.

**Nota:** Na Fase 1 com LangGraph Server, o checkpointer Postgres já é provido pelo servidor.
O gap real é a falta de `user_id` para isolar threads por usuário — bloqueado pelo P3 (auth).

**Evolução por fase:**
```
Fase 1 (agora): InMemoryCheckpointer → reseta em restart
Fase 2:         PostgresSaver(DATABASE_URL) → persiste, isolado por thread_id
Fase 3:         Vertex AI Agent Engine Sessions → managed, HIPAA compliant
```

---

### P3 — Autenticação de usuário

**Problema:** Só existe token de serviço compartilhado (`LANGGRAPH_AUTH_TOKEN`). Sem identidade
de usuário, sem JWT, sem sessão individual. Qualquer um com o token acessa dados de todos.

**Decisão:** Clerk (free tier) ou Auth0 — o `user_id` autenticado passa a ser o `thread_id`
do checkpointer LangGraph, conectando sessão, memória e auditoria. Desbloqueia P2 e P7.

**Evolução por fase:**
```
Fase 1: token fixo compartilhado
Fase 2: Clerk/Auth0 JWT → nginx valida → user_id no contexto do agente
Fase 3: Amazon Cognito / Firebase Auth (free até 50k MAU)
```

---

### P4 — Guardrails de input e output

**Problema:** Sem validação de entrada nem filtragem de saída. O agente está exposto a:
- **Input:** prompt injection, jailbreak, tópicos off-scope (não médicos), PII enviado pelo
  usuário (CPF, número de cartão) que pode ser logado ou vazado
- **Output:** resposta do LLM pode conter PII do paciente, informações médicas incorretas,
  ou conteúdo fora do escopo da clínica

**Decisão:** Dois pontos de controle no grafo — antes e depois do LLM:

```
[input] → validate_input → chat_with_llm → validate_output → [resposta ao usuário]
```

**validate_input** (novo nó LangGraph):
```python
def validate_input(state: AgendAIState) -> dict:
    text = state["input"]
    if is_injection(text):      return {"blocked": True, "reason": "prompt_injection"}
    if is_off_scope(text):      return {"blocked": True, "reason": "off_scope"}
    if contains_pii(text):      return {"blocked": True, "reason": "pii_detected"}
    return state
```

**validate_output** (novo nó LangGraph):
```python
def validate_output(state: AgendAIState) -> dict:
    response = state["messages"][-1].content
    if contains_pii(response):      redact_pii(response)
    if is_off_scope(response):      return {"response": FALLBACK_MESSAGE}
    return state
```

**Evolução por fase:**
```
Fase 1/2: nós manuais (regex + lista de padrões)
Fase 3:   AWS Bedrock Guardrails via ApplyGuardrail API
          → funciona com GPT-4o-mini sem trocar de LLM
          → configuração no console AWS: checkboxes, sem código
```

**Tipos de verificação:**

| Verificação | Input | Output | Fase 1/2 | Fase 3 |
|-------------|-------|--------|----------|--------|
| Prompt injection | ✅ | — | regex patterns | Bedrock |
| Off-scope (não médico) | ✅ | ✅ | lista de tópicos | Bedrock |
| PII detection | ✅ | ✅ | regex CPF/email/tel | Bedrock |
| Conteúdo tóxico | — | ✅ | lista de palavras | Bedrock |
| Informação médica incorreta | — | ✅ | — | Bedrock |

---

### P5 — Logs estruturados + correlation IDs

**Problema:** Sem `request_id` propagado entre nginx → API → agente → LangSmith. Impossível
correlacionar um erro do usuário com o trace correto no LangSmith.

**Decisão:** Middleware Express gerando `request_id` (UUID) por request, propagado nos headers
(`X-Request-ID`) e nos logs de cada serviço. No agente Python: `structlog` com output JSON.
Liga `request_id` ao `trace_id` do LangSmith via metadata.

```
nginx (X-Request-ID gerado) → API (loga com request_id) → agente (structlog JSON)
                                                                   ↓
                                                            LangSmith trace_id
```

---

### P6 — Context Manager

**Problema:** O agente acumula todas as mensagens da conversa na janela de contexto sem nenhum
gerenciamento. Em conversas longas, o contexto cresce indefinidamente, aumentando latência e
custo por token, e podendo exceder o limite de contexto do GPT-4o-mini (128k tokens).

**O que é context management:**
Decidir **o que entra na janela de contexto** enviada ao LLM a cada turno — não apenas
concatenar todas as mensagens anteriores.

**Estratégias:**

| Estratégia | Quando usar | Como |
|-----------|-------------|------|
| **Sliding window** | Conversas longas | Mantém últimas N mensagens |
| **Summarization** | Histórico volumoso | Resume mensagens antigas em um bloco |
| **Selective retrieval** | Memória longa (P7) | Busca mensagens relevantes via embedding |
| **Token budget** | Controle de custo | Trunca contexto ao atingir X tokens |

**Decisão para Fase 1/2:** Sliding window com summarization — mantém as últimas 10 trocas
completas e comprime o restante em um resumo injetado no system prompt.

```python
# agent/agent/context_manager.py
MAX_TURNS = 10
SUMMARY_PROMPT = "Resuma em 3 frases o histórico da conversa anterior:"

def trim_context(messages: list, llm) -> list:
    if len(messages) <= MAX_TURNS * 2:
        return messages
    old = messages[:-MAX_TURNS * 2]
    recent = messages[-MAX_TURNS * 2:]
    summary = llm.invoke([SystemMessage(SUMMARY_PROMPT)] + old)
    return [SystemMessage(f"[Resumo anterior]: {summary.content}")] + recent
```

**Evolução por fase:**
```
Fase 1/2: sliding window + summarization manual
Fase 3:   Vertex AI Memory Bank → extração semântica automática via Gemini
          → contexto enriquecido com fatos relevantes do paciente
```

---

### P7 — Memory Management (user, episodic, procedural)

**Problema:** O agente não tem memória além da conversa atual. Não sabe que o paciente João
prefere consultas às sextas, que já cancelou 2 vezes, ou que tem convênio Unimed. Cada sessão
começa do zero — a experiência não melhora com o uso.

**Três tipos de memória agêntica** (baseado em *Context Engineering: Sessions & Memory*,
Google Cloud, 2025):

#### Memória Episódica (curto prazo — o que aconteceu nesta conversa)

- **O que é:** Histórico da conversa atual — mensagens, tool calls, resultados
- **Status atual:** Existe via LangGraph checkpointer, mas sem `user_id` (gap do P2/P3)
- **Upgrade:** Após P2+P3, cada paciente tem seu thread isolado que persiste entre sessões
- **Fase 3:** Vertex AI Agent Engine Sessions — managed, isolado por user, HIPAA compliant

```python
# Com PostgresSaver (Fase 2):
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
graph = workflow.compile(checkpointer=checkpointer)
# thread_id = user_id → cada paciente tem seu histórico
```

#### Memória de Usuário (longo prazo — fatos sobre o paciente)

- **O que é:** Fatos semânticos extraídos das conversas e armazenados persistentemente.
  Exemplo: "prefere manhã", "tem fobia de dentista", "usa convênio Amil"
- **Status atual:** Não existe
- **Fase 2:** Tabela `patient_memory` no Postgres + extração manual via prompt
- **Fase 3:** Vertex AI Memory Bank (GA) — extração semântica automática via Gemini,
  busca por relevância, sem pipeline ETL manual

```python
# Fase 2 — extração manual:
def extract_user_facts(messages: list, llm) -> list[str]:
    return llm.invoke(EXTRACT_FACTS_PROMPT + messages)

# Fase 3 — Vertex AI Memory Bank:
memory = MemoryBankServiceClient()
user_context = memory.retrieve_memories(
    agent_engine_id=RUNTIME_ID,
    user_id=state.user_id,
    query=state.input
)
system_prompt = f"{BASE_PROMPT}\n\nContexto do paciente:\n{user_context}"
```

#### Memória Procedural (como o agente deve se comportar)

- **O que é:** Regras, personalidade, fluxos e ferramentas do agente — encoded no system
  prompt e na definição do grafo LangGraph
- **Status atual:** Existe implicitamente no system prompt de `llm_core.py` e nos nós do grafo
- **Gap:** Não é versionada nem testada explicitamente como "memória"
- **Upgrade:** Externalizar o system prompt para arquivo versionado + testes de comportamento
  que verificam que o agente segue as regras procedurais

```python
# agent/agent/prompts/system_prompt.py (versionado)
SYSTEM_PROMPT = """
Você é o assistente de agendamento da Clínica AgendAI.
Regras:
1. Só agende consultas para pacientes cadastrados no sistema
2. Confirme sempre data, hora e médico antes de criar o agendamento
3. Nunca revele dados de outros pacientes
"""
```

**Evolução da memória por fase:**

```
           | Episódica        | Usuário              | Procedural
-----------|------------------|----------------------|------------------
Fase 1     | InMemory (reset) | Não existe           | System prompt fixo
Fase 2     | PostgresSaver    | Tabela patient_memory| Arquivo versionado
Fase 3     | Agent Engine     | Vertex Memory Bank   | + testes de comportamento
           | Sessions (GCP)   | (extração automática)|
```

---

## Prioridade de Implementação

| P | Gap | Esforço | Impacto | Fase | Status |
|---|-----|---------|---------|------|--------|
| P1 | Retry + Circuit Breaker | ~2h | Elimina erros silenciosos | 1/2 | ADR-024 |
| P2 | Sessão persistente | ~2h | Conversas sobrevivem a restarts | 1/2 | Bloqueado por P3 |
| P3 | Auth de usuário | ~1 dia | Identidade + segurança | 2 | Desbloqueia P2/P7 |
| P4 | Guardrails input+output | ~4h | Segurança de conteúdo | 2/3 | Bedrock na Fase 3 |
| P5 | Logs estruturados | ~3h | Observabilidade end-to-end | 2 | — |
| P6 | Context Manager | ~3h | Custo + latência em conv. longas | 2 | — |
| P7 | Memory Management | ~1 semana | Experiência personalizada | 2/3 | Bloqueado por P2/P3 |

---

## Acceptance Criteria por gap

### P1 (Retry + Circuit Breaker)
1. `RateLimitError` em `llm_core.py` → retry automático, usuário não vê erro na 1ª falha
2. 3 falhas consecutivas ao OpenAI → circuit breaker abre, erro claro em <1s
3. Cold start do Render na API → agente aguarda e retenta, não falha imediatamente
4. Startup da API não falha se Postgres demorar até 30s
5. 70 pytest + 39 Jest continuam passando

### P4 (Guardrails input+output)
1. Input com padrão de prompt injection → bloqueado antes de chamar o LLM
2. Input off-scope (ex: "me ajude a escrever código") → recusado com mensagem clara
3. Output com PII do paciente → redactado antes de chegar ao usuário
4. Output off-scope → substituído por mensagem de fallback da clínica

### P6 (Context Manager)
1. Conversa com mais de 10 turnos → mensagens antigas resumidas, não truncadas abruptamente
2. Token count do contexto enviado ao LLM ≤ limite configurado
3. Resumo preserva fatos críticos (agendamentos feitos, cancelamentos, preferências)

### P7 (Memory Management — Fase 2)
1. Após agendamento, fato "paciente agendou com Dr. X" é salvo na memória do usuário
2. Na próxima sessão, o agente sabe que o paciente já consultou antes
3. Memória episódica (thread) sobrevive a restart do servidor (bloqueado por P2+P3)

---

## Dependências entre gaps

```
P3 (auth) ──────────────────────► P2 (sessão por user_id)
                                        │
                                        ▼
                                   P7 (memória — precisa de user_id para isolar)

P1 (retry) ─── independente ──── pode implementar agora

P4 (guardrails) ─── independente ─── pode implementar agora (Bedrock na Fase 3)

P5 (logs) ─── independente ──── pode implementar agora

P6 (context) ─── parcialmente independente ─── não precisa de P3, mas se beneficia de P7
```

---

## Out of Scope desta spec (Fases 2/3 ou Specs separadas)

- Terraform / Cloud IaC → Spec 006
- Vertex AI Memory Bank (extração automática) → Spec 007
- AWS Bedrock Guardrails (managed) → Spec 007
- Vertex AI Agent Engine Sessions → Spec 007
- Amazon Cognito / Firebase Auth → pode ser P3 desta spec ou Spec 007
- Vertex AI Evaluation (quality gate no CI/CD) → Spec 007
