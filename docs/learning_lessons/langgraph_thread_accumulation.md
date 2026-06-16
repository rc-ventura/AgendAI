# LangGraph Thread Accumulation: threads/search sem limite degrada com o tempo

**Context:** Descoberto em produção (Render) durante validação com Playwright após o fix de SSE. O `threads/search` retornou 2,6MB em ~3–4s num ambiente com ~12 threads de debug acumuladas.
**Date:** 2026-06-16

---

## Problema

O endpoint `POST /threads/search` do LangGraph Server retorna **todos os threads** do banco sem paginação por padrão. Cada thread carrega seu estado completo (checkpoints + blobs). Sem isolamento por usuário, todos os threads de todas as sessões de debug/teste acumulam no mesmo banco.

```
POST /threads/search 200 3565ms  response_size_bytes=2660748
```

Isso se manifesta como:
- Lentidão progressiva na abertura da UI (piora a cada thread criada)
- Cold start do banco Neon após o primeiro request pesado
- Em free tier: pode atingir limites de storage do plano gratuito

---

## Por que acontece

O LangGraph Server usa Postgres para persistir checkpoints (via `PostgresSaver`). Cada turno de conversa grava:
- 1 registro em `checkpoints`
- N registros em `checkpoint_blobs` (um por chave do state)
- N registros em `checkpoint_writes`

Uma thread de 4 trocas gera ~20–40 linhas distribuídas nessas tabelas. Com 12 threads de debug = centenas de linhas, resultando em ~2,6MB no `threads/search`.

---

## Solução curto prazo: limpar o banco

```sql
-- Neon dashboard → SQL Editor → banco agendai_lg
TRUNCATE threads CASCADE;
-- CASCADE propaga para: runs, checkpoints, checkpoint_blobs, checkpoint_writes
```

**TRUNCATE e não DROP**: DROP remove a estrutura da tabela — o LangGraph Server quebraria. TRUNCATE remove apenas os dados, mantém a estrutura intacta.

**Nunca truncar `checkpoint_migrations`** — controla quais migrações de schema foram aplicadas. Se apagada, o servidor tenta reaplicar tudo e pode falhar.

| Tabela | Limpar com TRUNCATE? |
|---|---|
| `threads` | ✅ (CASCADE propaga) |
| `runs` | ✅ (via CASCADE) |
| `checkpoints` | ✅ (via CASCADE) |
| `checkpoint_blobs` | ✅ (via CASCADE) |
| `checkpoint_writes` | ✅ (via CASCADE) |
| `checkpoint_migrations` | ❌ nunca |

---

## Solução curto prazo: limitar o SDK

O `threads/search` aceita `limit`. Configurar na inicialização do client na UI evita buscar todos de uma vez:

```typescript
await client.threads.search({ limit: 20 });
```

Reduz o payload de 2,6MB para ~20–100KB independente de quantos threads existem no banco.

---

## Solução longo prazo: isolamento por usuário (Spec 006)

Com autenticação (JWT via Clerk/Auth0), cada thread recebe `metadata: { user_id }` na criação. O `threads/search` passa a filtrar por usuário:

```typescript
await client.threads.search({
  metadata: { user_id: "usr_abc123" },
  limit: 20,
});
```

O servidor retorna apenas os threads daquele paciente. Threads de outros usuários ficam invisíveis. O payload cai para ~5–20KB independente do volume total no banco.

---

## Relação com ADRs e próximos passos

- **Spec 006** — auth + user_id é o pré-requisito para isolamento de threads
- **Fase 3** — Agent Engine Sessions (Vertex AI) entrega TTL automático e cleanup por inatividade sem precisar gerenciar SQL manualmente
