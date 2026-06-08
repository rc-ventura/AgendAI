# Feature Specification: Spec 007 — Memória de Longo Prazo + Human-in-the-Loop

**Feature Branch**: `007-memory-hitl`

**Created**: 2026-06-07

**Updated**: 2026-06-07

**Status**: Draft

**Depende de**: [Spec 006](../006-auth-session/spec.md) — `user_id` autenticado é prerequisito  
**Input**: Whitepapers *Context Engineering: Sessions & Memory* e *Agentic Design Patterns* (Google Cloud, 2025)

---

## Why This Feature Exists

Com autenticação e sessão persistente em produção (Spec 006), o sistema tem identidade de
usuário. Esta spec usa essa identidade para duas evoluções:

1. **Memória de longo prazo**: o agente aprende com conversas anteriores — preferências do
   paciente, histórico de cancelamentos, convênio. Cada sessão não começa mais do zero.

2. **Human-in-the-Loop (HITL)**: antes de executar ações irreversíveis (criar ou cancelar
   agendamento), o agente confirma com o usuário. Elimina agendamentos acidentais por
   interpretação errada do LLM.

---

## Gaps Mapeados

### P7 — Memory Management

**Três tipos de memória agêntica:**

#### Memória Episódica (sessão atual)
- Já entregue pela Spec 006 (threads persistentes por `user_id`)
- Fase 3: Vertex AI Agent Engine Sessions — managed, HIPAA compliant

#### Memória de Usuário (longo prazo — fatos do paciente)

Fatos semânticos extraídos das conversas e armazenados persistentemente:
> "prefere consultas às sextas", "já cancelou 2 vezes", "usa convênio Amil"

**Fase 2 (esta spec):**
```python
# Nova tabela no Postgres
# api/db/schema.sql
CREATE TABLE patient_memory (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

# Extração manual via prompt após cada conversa:
def extract_user_facts(messages: list, llm) -> list[str]:
    return llm.invoke(EXTRACT_FACTS_PROMPT + messages)

# Injeção no system prompt da próxima sessão:
facts = db.query("SELECT fact FROM patient_memory WHERE user_id = $1", user_id)
system_prompt = f"{BASE_PROMPT}\n\nContexto do paciente:\n{chr(10).join(facts)}"
```

**Fase 3:**
```python
# Vertex AI Memory Bank — extração semântica automática via Gemini
memory = MemoryBankServiceClient()
user_context = memory.retrieve_memories(
    agent_engine_id=RUNTIME_ID,
    user_id=state.user_id,
    query=state.input
)
```

#### Memória Procedural (regras do agente)
- Externalizar o system prompt de `llm_core.py` para `agent/agent/prompts/system_prompt.py`
- Versionar explicitamente + testes de comportamento que verificam regras procedurais

```python
# agent/agent/prompts/system_prompt.py
SYSTEM_PROMPT = """
Você é o assistente de agendamento da Clínica AgendAI.
Regras:
1. Só agende consultas para pacientes cadastrados no sistema
2. Confirme sempre data, hora e médico antes de criar o agendamento
3. Nunca revele dados de outros pacientes
"""
```

**Evolução por fase:**
```
           | Episódica             | Usuário                | Procedural
-----------|-----------------------|------------------------|--------------------
Spec 006   | PostgresSaver por user| Não existe             | System prompt fixo
Spec 007   | PostgresSaver por user| Tabela patient_memory  | Arquivo versionado
Fase 3     | Agent Engine Sessions | Vertex Memory Bank     | + testes comportamento
```

---

### P9 — Human-in-the-Loop (HITL)

**Problema:** O agente executa ações irreversíveis (criar/cancelar agendamento) sem pedir
confirmação. Um mal-entendido do LLM pode criar uma consulta que o paciente não queria.

**Implementação via `interrupt()` nativo do LangGraph:**

```python
from langgraph.types import interrupt

async def confirm_action(state: AgendAIState) -> dict:
    if state.get("email_payload"):
        decision = interrupt({
            "message": "Confirmar agendamento?",
            "medico": state["email_payload"]["medico_nome"],
            "data_hora": state["email_payload"]["data_hora"],
        })
        if not decision["confirmed"]:
            return {"email_pending": False, "email_payload": None}
    return state
```

**Fluxo:**
```
chat_with_llm → [LLM decide criar agendamento]
      ↓
 confirm_action ──── interrupt() ────► UI mostra confirmação ao paciente
      │                                         │
      │                                 paciente confirma / cancela
      │                                         │
      └──────────── resume ────────────────────┘
      ↓
execute_tools → criar_agendamento → process_tool_results → send_email
```

**Requisito**: `interrupt()` requer checkpointer persistente para salvar estado enquanto aguarda
resposta do usuário — entregue pela Spec 006 (PostgresSaver via managed LangGraph Server).

**Alternativa sem depender de P2**: `HumanInTheLoopMiddleware` via `create_agent` (P8 da Spec
005) — gerenciamento de estado interno, não persiste entre sessões mas não depende de auth.

---

## Acceptance Criteria

### P7 (Memory Management)
1. Após agendamento, fato "paciente agendou com Dr. X" é salvo em `patient_memory`
2. Na próxima sessão, o system prompt já inclui fatos do paciente
3. Fato duplicado não é inserido duas vezes
4. Paciente pode pedir para o agente "esquecer" uma preferência → deletado da tabela
5. 70 pytest + 39 Jest continuam passando

### P9 (HITL)
1. LLM decide criar agendamento → UI exibe modal de confirmação com médico e horário
2. Paciente cancela no modal → agendamento não é criado, email não é enviado
3. Paciente confirma → agendamento criado normalmente
4. Timeout de 5 min sem resposta → run expira com mensagem clara
5. HITL não quebra o fluxo de áudio (transcribe → confirm → tts)

---

## Out of Scope desta spec

- Roles e permissões (médico vs paciente vs admin) → Spec futura
- Vertex AI Memory Bank (extração automática) → Fase 3
- Vertex AI Agent Engine Sessions → Fase 3
- AWS Bedrock Guardrails → Fase 3
- Compliance LGPD formal → Spec futura

---

## Referências

- [Spec 006](../006-auth-session/spec.md) — prerequisito (`user_id`)
- [Spec 005](../005-agent-hardening/spec.md) — P8 (`create_agent` middleware, alternativa HITL)
- [ADR-014](../../docs/adr/ADR-014-checkpointer-inmem.md) — checkpointer in-memory (supersedido)
- [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) — estratégia de checkpoint
- *Context Engineering: Sessions & Memory* — Google Cloud, 2025
