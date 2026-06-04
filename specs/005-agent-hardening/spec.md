# Feature Specification: Spec 005 — Agent Hardening (Production-Grade Resilience)

**Feature Branch**: `005-agent-hardening`

**Created**: 2026-06-03

**Status**: Draft

**Input**: Análise de gaps agênticos mapeados no `docs/AgendAI_Architecture_Roadmap.pdf` (V2.0)
e observações de produção na Fase 1 (Render). Baseado nos whitepapers *Prototype to Production*,
*Context Engineering: Sessions & Memory* e *Agentic Design Patterns* (Google Cloud, 2025).

---

## Why This Feature Exists

O AgendAI está em produção na Fase 1 (Render + GitHub Actions). A análise de gaps agênticos
identificou que, apesar de funcionar, o sistema não é production-grade: chamadas ao OpenAI caem
silenciosamente sem retry, o agente não tem circuit breaker para falhas da LLM, a API Node.js
não sobrevive a falhas transientes do Postgres, e não há identidade de usuário ou guardrails de
input. Esses gaps transformam falhas isoladas em erros permanentes visíveis ao usuário.

Esta spec endereça os 5 gaps em ordem de impacto × esforço, conforme o roadmap V2.0.

---

## Gaps Mapeados (P1 → P5)

### P1 — Retry + Circuit Breaker no agente (este ADR)

**Problema:** `llm_core.py`, `transcriber.py` e `api_client.py` não têm retry. Uma falha
transiente da OpenAI (RateLimitError, APITimeoutError) ou da API interna (cold start no Render)
encerra o run do grafo permanentemente. `tts.py` e `email_sender.py` já têm tenacity.

**Decisão técnica:** Ver [ADR-024](../../docs/adr/ADR-024-retry-resilience-strategy.md).

**Escopo:**
- `agent/agent/nodes/llm_core.py` — retry + circuit breaker (pybreaker)
- `agent/agent/nodes/transcriber.py` — retry tenacity
- `agent/agent/api_client.py` — retry tenacity em todos os 6 métodos HTTP
- `api/src/db/connection.js` — retry async-retry no startup
- `api/src/repositories/*.js` — retry p-retry em queries transientes

---

### P2 — Sessão persistente por usuário

**Problema:** `InMemoryCheckpointer` (ADR-014) reseta em restart. Conversas não sobrevivem a
redeploys. Cada restart do `langgraph-server` apaga o histórico de todos os threads.

**Decisão:** Migrar para `PostgresSaver` (Fase 1-2) ou Agent Engine Sessions GCP (Fase 3).
Cada conversa ganha um `thread_id` por `user_id` e sobrevive a restarts.

**Nota:** Na Fase 1 com LangGraph Server, o checkpointer Postgres já é provido pelo servidor —
o gap é na configuração do `thread_id` por usuário, não na persistência em si.

---

### P3 — Autenticação de usuário

**Problema:** Só existe token de serviço compartilhado (`LANGGRAPH_AUTH_TOKEN`). Sem identidade
de usuário, sem JWT, sem sessão individual. Qualquer um com o token acessa dados de todos.

**Decisão:** Clerk (free tier) ou Auth0 — o `user_id` autenticado passa a ser o `thread_id`
do checkpointer LangGraph, conectando sessão, memória e auditoria.

---

### P4 — Guardrails de input

**Problema:** Sem validação contra prompt injection, tópicos off-scope para a clínica, ou PII
no input. Um usuário pode instruir o agente a ignorar suas regras.

**Decisão:** Novo nó LangGraph `validate_input` antes do `chat_with_llm`. Verifica: (a) padrões
de prompt injection, (b) tópicos fora do escopo médico, (c) PII no input. Fase 3 substitui por
AWS Bedrock Guardrails (zero código adicional).

---

### P5 — Logs estruturados + correlation IDs

**Problema:** Sem `request_id` propagado entre nginx → API → agente → LangSmith. Impossível
correlacionar um erro do usuário com o trace correto no LangSmith.

**Decisão:** Middleware Express gerando `request_id` (UUID) por request, propagado nos logs.
No agente Python: `structlog` com output JSON. Liga `request_id` ao `trace_id` do LangSmith.

---

## Prioridade de Implementação

| P | Gap | Esforço | Impacto | Status |
|---|-----|---------|---------|--------|
| P1 | Retry + Circuit Breaker | ~2h | Elimina erros silenciosos em produção | **Este spec** |
| P2 | Sessão persistente | ~2h | Conversas sobrevivem a restarts | Próxima iteração |
| P3 | Auth de usuário | ~1 dia | Segurança por identidade | Fase 2 |
| P4 | Guardrails de input | ~4h | Segurança de conteúdo | Fase 2 |
| P5 | Logs estruturados | ~3h | Observabilidade end-to-end | Fase 2 |

---

## Acceptance Criteria (P1)

1. Uma falha transiente da OpenAI (`RateLimitError`, `APITimeoutError`) em `llm_core.py`
   resulta em retry automático — o usuário não vê erro na primeira falha.
2. Após 3 falhas consecutivas ao OpenAI, o circuit breaker abre e retorna erro claro ao
   usuário em vez de travar o grafo.
3. Uma falha de conexão em `api_client.py` (cold start do Render) resulta em retry — o agente
   aguarda a API acordar antes de desistir.
4. O startup da API Node.js não falha se o Postgres demorar até 30s para ficar disponível.
5. Todos os 70 testes pytest + 39 Jest continuam passando após as mudanças.

---

## Out of Scope (P2–P5 e Fases 2/3)

- PostgresSaver / Agent Engine Sessions (P2)
- Clerk / Auth0 / Amazon Cognito (P3)
- Bedrock Guardrails (P4 Fase 3)
- structlog / correlation IDs (P5)
- Terraform / Cloud IaC (Spec 006)
- Vertex AI Memory Bank (Spec 007)
