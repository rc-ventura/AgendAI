# Feature Specification: Spec 006 — Autenticação + Sessão Persistente por Usuário

**Feature Branch**: `006-auth-session`

**Created**: 2026-06-07

**Updated**: 2026-06-07

**Status**: Draft

**Depende de**: [Spec 005](../005-agent-hardening/spec.md) (retry + logs em produção antes de adicionar auth)  
**Desbloqueia**: [Spec 007](../007-memory-hitl/spec.md) (memória e HITL precisam de `user_id`)

---

## Why This Feature Exists

O AgendAI expõe um único token de serviço compartilhado (`LANGGRAPH_AUTH_TOKEN`). Qualquer
usuário com o token acessa dados de todos os outros e compartilha o mesmo contexto de conversa.
Sem identidade de usuário não é possível isolar sessões, construir memória por paciente ou
implementar HITL com estado persistente.

Esta spec entrega o `user_id` autenticado como primitivo central — tudo que vem depois
(memória, auditoria, HITL, compliance) depende dele.

---

## Gaps Mapeados

### P3 — Autenticação de usuário

**Problema:** Token fixo compartilhado — sem JWT, sem identidade individual, sem sessão isolada.

**Decisão a tomar:** Clerk vs Auth0 vs solução própria.

| Provider | Free tier | JWT built-in | nginx integration | Complexidade |
|----------|-----------|-------------|-------------------|--------------|
| **Clerk** | 10k MAU | ✅ | ✅ middleware | Baixa — SDK React pronto |
| **Auth0** | 7.5k MAU | ✅ | ✅ | Baixa — mais corporativo |
| **Supabase Auth** | Ilimitado OSS | ✅ | Manual | Média — infra própria |
| **JWT próprio** | — | Manual | Manual | Alta — reescrever tudo |

**Fluxo proposto:**
```
Paciente faz login (Clerk/Auth0)
    ↓
JWT emitido com user_id
    ↓
nginx valida JWT em todas as requests (lua-jwt ou jwks endpoint)
    ↓
user_id propagado no header X-User-ID para API e agente
    ↓
thread_id do LangGraph = user_id → sessão isolada por paciente
```

**Escopo de implementação:**
- Provider de auth integrado na UI (`agent-ui-pro`)
- nginx: validação JWT + extração de `user_id` → header `X-User-ID`
- API: middleware recebendo `X-User-ID` para auditoria de logs
- Agente: `user_id` como `thread_id` no LangGraph checkpointer

---

### P2 — Sessão persistente por usuário

**Problema:** O LangGraph Server já usa Postgres como backend de checkpointer — o gap real é
a ausência de `user_id` para isolar threads. Hoje todos os pacientes compartilham o mesmo
namespace de threads.

**Solução após P3:** Usar `user_id` autenticado como `thread_id`:

```python
# agent-ui-pro: criar thread com user_id
const thread = await client.threads.create({
  metadata: { user_id: userId }
})
```

**Resultado:**
- Histórico de conversa persiste entre sessões do mesmo paciente
- Threads isolados — paciente A não vê conversas do paciente B
- Sobrevive a redeploys (Postgres já é persistente no managed server)

**Evolução:**
```
Fase 2 (esta spec): thread_id = user_id → isolamento via LangGraph Server
Fase 3:             Vertex AI Agent Engine Sessions → managed, HIPAA compliant
```

---

## Acceptance Criteria

### P3 (Autenticação)
1. Paciente sem login tenta acessar a UI → redirecionado para tela de login
2. Token expirado → refresh automático ou redirect para login sem erro visível
3. nginx rejeita request sem JWT válido com 401 antes de chegar ao agente
4. `user_id` está disponível no contexto do agente via header `X-User-ID`
5. Dois pacientes logados simultaneamente não veem as conversas um do outro

### P2 (Sessão persistente)
1. Paciente fecha o browser e reabre → histórico de conversa é restaurado
2. Redeploy do agente (langgraph-server) → threads anteriores continuam acessíveis
3. Sidebar da UI lista threads históricos do usuário autenticado
4. 70 pytest + 39 Jest continuam passando

---

## Out of Scope desta spec

- Memory Management (fatos do paciente) → [Spec 007](../007-memory-hitl/spec.md)
- Human-in-the-Loop → [Spec 007](../007-memory-hitl/spec.md)
- Roles e permissões (médico vs paciente vs admin) → Spec futura
- Compliance LGPD formal → Spec futura
- MFA / 2FA → Spec futura

---

## Referências

- [Spec 005](../005-agent-hardening/spec.md) — prerequisito
- [Spec 007](../007-memory-hitl/spec.md) — desbloqueia
- [ADR-017](../../docs/adr/ADR-017-api-security-tokens.md) — token de serviço atual
- [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) — estratégia de checkpoint
