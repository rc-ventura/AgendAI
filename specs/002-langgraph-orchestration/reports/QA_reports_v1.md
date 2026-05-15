# QA Report — Spec 002: LangGraph Medical Scheduling Orchestration

**Versão**: v1 | **Data**: 2026-05-15 | **QA Engineer**: Cascade (AI-assisted)
**Método**: Análise estática + execução de 83 testes automatizados

---

## Sumário Executivo

| Área | Avaliação |
|------|-----------|
| Qualidade da Spec | ⚠️ Bom, com gaps de documentação |
| Cobertura de Testes | 🔴 Insuficiente (módulo crítico sem testes) |
| Bugs Críticos | 🔴 2 bugs que quebram funcionalidade core |
| Segurança | 🔴 2 vulnerabilidades críticas |
| **Veredito de Produção** | **❌ NÃO APROVADO — requer correções** |

---

## 1. Resultados da Execução de Testes

| Suite | Framework | Testes | Status |
|-------|-----------|--------|--------|
| `agent/` | pytest | 28 | ✅ 28 pass |
| `agent-ui/` | Vitest | 21 | ✅ 21 pass |
| `api/` | Jest | 34 | ✅ 34 pass |
| **Total** | | **83** | **✅ 83 pass** |

**Nota**: Testes passando ≠ cobertura adequada. A análise abaixo revela gaps significativos.

---

## 2. Qualidade dos Artefatos da Spec

### 2.1 Pontos Fortes

- **`spec.md`**: 6 user stories com acceptance criteria Given/When/Then, edge cases, 10 FRs, success criteria mensuráveis
- **`plan.md`**: Technical context, constitution check, estrutura de diretórios, diagrama de grafo
- **`data-model.md`**: Definição precisa do `AgendAIState`, tools, `EmailPayload`, entidades da Platform API
- **`tasks.md`**: 65 tasks organizadas em fases com dependências e checkpoints
- **`research.md`**: 6 decisões técnicas com rationale e alternativas rejeitadas
- **`contracts/`**: Contrato REST + SSE bem especificado

### 2.2 Gaps e Inconsistências

| ID | Sev | Descrição |
|----|-----|-----------|
| DOC-01 | 🔴 HIGH | `tool_result_processor.py` — nó crítico ponte tools→email — **não documentado em nenhum artefato** |
| DOC-02 | 🟡 MED | Diagrama em `plan.md` mostra `router_email`/`router_audio` como nós; implementação usa conditional edges + `process_tool_results` |
| DOC-03 | 🟡 MED | `research.md` recomenda `tools_condition`; código usa `route_after_llm` customizada |
| DOC-04 | 🟢 LOW | FR-001 menciona `POST /chat`; real é protocolo LangGraph Platform |
| DOC-05 | 🟢 LOW | `quickstart.md` descreve resposta de áudio como "texto", contradizendo spec |

### 2.3 Checklist de Requirements

Checklist marca "No implementation details" ✅ mas `spec.md` contém "GPT-4o-mini", "Whisper", "TTS". Preenchimento acrítico.

---

## 3. Auditoria Implementação vs Spec

### 3.1 Mapeamento FR → Código

| FR | Descrição | Status |
|----|-----------|--------|
| FR-001 | Endpoint HTTP texto/áudio | ✅ (protocolo diferente) |
| FR-002 | StateGraph com 4 fluxos | ✅ (7 nós) |
| FR-003 | 5 tools function calling | ✅ |
| FR-004 | Integração API REST | ✅ |
| FR-005 | Whisper STT + TTS | ✅ |
| FR-006 | Email Gmail agendamento/cancelamento | ⚠️ Bugs — ver seção 5 |
| FR-007 | LangSmith tracing | ✅ |
| FR-008 | Resposta no idioma do paciente | ✅ |
| FR-009 | LangGraph Platform + Agent UI | ✅ |
| FR-010 | Compatibilidade SQLite | ✅ |

### 3.2 Componente Não Documentado

| Arquivo | Função | Documentado |
|---------|--------|-------------|
| `nodes/tool_result_processor.py` | Extrai ToolMessages → `email_pending`/`email_payload` | ❌ Nenhum artefato |

---

## 4. Cobertura de Testes por User Story

| US | Cobertura | Gaps |
|----|-----------|------|
| US1 Consultar horários (P1) | ⚠️ Parcial | Sem teste lista vazia, sem integração completa |
| US2 Agendar (P1) | ⚠️ Parcial | Sem teste fluxo completo com tool loop |
| US3 Cancelar (P2) | 🔴 Insuficiente | Sem teste de integração |
| US4 Áudio (P2) | ⚠️ Parcial | Sem teste áudio corrompido |
| US5 LangSmith (P2) | ⚠️ Parcial | Apenas smoke test |
| US6 Pagamentos (P3) | 🔴 Insuficiente | Sem teste de integração |

### Edge Cases — 0 de 7 cobertos

Nenhum dos 7 edge cases de `spec.md` tem teste: LLM sem intenção, API down, email fail, concorrência, horário ocupado, já cancelado, áudio corrompido.

### Módulo Sem Cobertura

`tool_result_processor.py` (79 linhas, 4 funções): **zero testes**.
- `_find_last_tool_call_name()`, `_build_email_payload()`, `_extract_field()`, `process_tool_results()`

---

## 5. Bugs e Falhas Críticas

### 🔴 BUG-01 [CRITICAL]: `_extract_field` não extrai campos essenciais

**Arquivo**: `agent/agent/nodes/tool_result_processor.py:49-70`
**Impacto**: Emails sem nome do paciente, valor e formas de pagamento

Handlers existem só para `paciente_email`, `data_hora`, `medico_nome`. Campos `paciente_nome`, `valor`, `formas_pagamento` **sempre retornam None**:

```python
"paciente_nome": _extract_field(state, "paciente_nome") or "Paciente",  # → "Paciente"
"valor": _extract_field(state, "valor"),          # → None
"formas_pagamento": _extract_field(state, "formas_pagamento"),  # → None
```

Quebra acceptance criteria US2 — email sem dados completos.

---

### 🔴 BUG-02 [CRITICAL]: SMTP síncrono bloqueia event loop

**Arquivo**: `agent/agent/nodes/email_sender.py:64`
**Impacto**: Event loop bloqueado 30s+ durante envio com retries

```python
async def send_email(state: AgendAIState) -> dict:
    ...
    _send_smtp(subject, body, payload["paciente_email"])  # ← BLOQUEANTE
```

`_send_smtp` é síncrona com `@retry` (3 tentativas, backoff 2-10s). Em produção multi-usuário, degrada todas as requisições.

**Correção**: `asyncio.to_thread()` ou `loop.run_in_executor()`.

---

### 🟡 BUG-03 [HIGH]: Grafo sem checkpointer

**Arquivo**: `agent/agent/graph.py:59`

```python
graph = builder.compile()  # sem checkpointer=
```

Spec menciona SQLite checkpointer. Histórico 100% volátil.

---

### 🟡 BUG-04 [HIGH]: Extração frágil por regex

**Arquivo**: `agent/agent/nodes/tool_result_processor.py:49-70`

Regex dependem de padrões textuais: `Dr\.?\s+[\w\s]+` falha para "Dra. Ana", formato de data rígido. Sem logging de fallback.

---

### 🟡 BUG-05 [HIGH]: Singleton `get_client()` não thread-safe

**Arquivo**: `agent/agent/api_client.py:46-53`

Race condition em `if _client is None` — múltiplos clients em cenários concorrentes.

---

### 🟢 BUG-06 [LOW]: `tts.py:24` — `response.read()` síncrono

Impacto mínimo para áudios pequenos, mas tecnicamente incorreto.

---

## 6. Testes Críticos Faltantes

### 🔴 Prioridade Crítica

| ID | Teste |
|----|-------|
| TST-01 | Unitários `tool_result_processor.py` (4 funções, zero cobertura) |
| TST-02 | Integração fluxo completo US2 (chat→tools→process→chat→email) |
| TST-03 | API REST indisponível → graceful degradation (SC-007) |

### 🟡 Prioridade Alta

| ID | Teste |
|----|-------|
| TST-04 | Integração fluxo US3 (cancelamento→email) |
| TST-05 | Email fail após 3 retries → sistema continua |
| TST-06 | Áudio corrompido → erro (US4 scenario 2) |
| TST-07 | Unitários funções roteamento (`route_after_input`, `route_after_llm`, `route_after_email`) |

### 🟢 Prioridade Média

| ID | Teste |
|----|-------|
| TST-08 | Horários vazios (US1 scenario 2) |
| TST-09 | Agendamento já cancelado (US3 scenario 2) |
| TST-10 | Paciente sem ID no cancelamento (US3 scenario 3) |
| TST-11 | Sessões simultâneas isoladas |

---

## 7. Auditoria de Segurança

### 🔴 SEC-01 [CRITICAL]: LangGraph Server sem autenticação

**Impacto**: Porta 8123 exposta sem auth. Acesso irrestrito para:
- Executar agente e consumir créditos OpenAI
- Acessar PII de pacientes (nome, email, telefone) via tools
- Criar/cancelar agendamentos

API REST tem rate limiting; agente não tem nenhuma proteção.

---

### 🔴 SEC-02 [CRITICAL]: Prompt injection sem mitigação

**Arquivo**: `agent/agent/nodes/llm_core.py:7-14`

Mensagens do usuário vão direto ao LLM sem sanitização. System prompt não tem proteção contra jailbreak. Um atacante pode:
- Fazer o agente ignorar tools e inventar dados
- Extrair o system prompt
- Redirecionar o comportamento do agente

---

### 🟡 SEC-03 [HIGH]: PII exposta em LangSmith traces

Ferramentas retornam nome, email, telefone de pacientes. Todo tool output é logado no LangSmith. Dados sensíveis em plataforma de terceiros.

---

### 🟡 SEC-04 [HIGH]: Gmail App Password em env var plaintext

Aceitável para demo, mas não production-grade. Sem vault/secret manager.

---

### 🟡 SEC-05 [HIGH]: Sem rate limiting no agente

API REST (`api/src/app.js:12-18`) tem `express-rate-limit` (100 req/15min). LangGraph server não tem equivalente.

---

### 🟢 SEC-06 [MEDIUM]: Sem CORS configurado no agent

### 🟢 SEC-07 [MEDIUM]: SMTP_SSL sem custom TLS verification

---

## 8. Veredito Final

### ❌ NÃO APROVADO PARA PRODUÇÃO

**Bloqueadores (must-fix antes de deploy)**:

1. **BUG-01**: `_extract_field` não extrai `paciente_nome`, `valor`, `formas_pagamento` — emails saem incompletos
2. **BUG-02**: Chamada SMTP síncrona bloqueia event loop — risco de degradação multi-usuário
3. **SEC-01**: LangGraph Server sem autenticação — acesso irrestrito a dados e créditos
4. **SEC-02**: Sem mitigação de prompt injection — risco de manipulação do agente
5. **TST-01**: `tool_result_processor.py` sem cobertura de testes — módulo crítico não validado

**Recomendações para aprovação condicional (demo/MVP interno)**:

Se o deploy for para ambiente interno/demo (não produção pública), os bugs BUG-01 e BUG-02 ainda precisam ser corrigidos. As vulnerabilidades SEC-01 e SEC-02 podem ser aceitas com documentação de risco se o ambiente for isolado.

### Plano de Correção Recomendado

| Ordem | Ação | Tipo |
|-------|------|------|
| 1 | Corrigir `_extract_field` — adicionar handlers para `paciente_nome`, `valor`, `formas_pagamento` | Bug fix |
| 2 | Tornar `_send_smtp` não-bloqueante com `asyncio.to_thread()` | Bug fix |
| 3 | Adicionar testes unitários para `tool_result_processor.py` | Test |
| 4 | Adicionar API key auth ou basic auth no LangGraph server | Security |
| 5 | Adicionar input sanitization e hardened system prompt | Security |
| 6 | Adicionar checkpointer ao `graph.compile()` | Feature |
| 7 | Implementar testes de integração US2, US3 e edge cases | Test |
| 8 | Adicionar rate limiting no agent | Security |

---

## Apêndice A — Arquivos Analisados

```
specs/002-langgraph-orchestration/
  spec.md, plan.md, data-model.md, tasks.md, research.md, quickstart.md
  contracts/langgraph-platform-api.md
  checklists/requirements.md

agent/
  agent/state.py, agent/graph.py, agent/api_client.py
  agent/nodes/input_detector.py, transcriber.py, llm_core.py
  agent/nodes/tools.py, tool_result_processor.py, email_sender.py, tts.py
  tests/conftest.py, test_state.py, test_api_client.py, test_nodes.py, test_graph.py

agent-ui/
  src/lib/langgraph.ts
  src/components/ChatWindow.tsx, AudioUploadButton.tsx
  src/tests/langgraph.test.ts, ChatWindow.test.tsx, AudioUploadButton.test.tsx

api/
  src/app.js

docker-compose.yml, agent/Dockerfile, agent/langgraph.json, agent/pyproject.toml
```

## Apêndice B — Contagem de Testes

| Categoria | Quantidade |
|-----------|------------|
| Testes de estado | 4 |
| Testes de API client | 7 |
| Testes de nós (tools) | 6 |
| Testes de nós (llm, email, transcriber, tts) | 5 |
| Testes de input detector | 2 |
| Testes de integração (graph) | 4 |
| **Subtotal agent** | **28** |
| Testes agent-ui (langgraph lib) | 9 |
| Testes agent-ui (ChatWindow) | 8 |
| Testes agent-ui (AudioUploadButton) | 4 |
| **Subtotal agent-ui** | **21** |
| Testes API REST | 34 |
| **TOTAL** | **83** |