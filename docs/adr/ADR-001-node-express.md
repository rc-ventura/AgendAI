# ADR-001: Stack da API REST — Node.js 20 + Express 4

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/)
**Código**: `api/src/app.js`, `api/src/server.js`, `api/package.json`

---

## Contexto

A API REST do AgendAI precisa gerenciar médicos, pacientes, horários, agendamentos e pagamentos com operações CRUD. O sistema é um MVP de demonstração — single-node, sem requisitos de escala horizontal, com carga simulada de até 10 usuários.

## Decisão

Usar **Node.js 20 LTS + Express 4** como stack da API REST, com `better-sqlite3` síncrono para banco, `node-cache` para cache in-process, e `jest` + `supertest` para testes.

## Alternativas consideradas

### Alternativa A: Python + FastAPI
**Por que não**: Exigiria reescrever toda a API quando o agente LangGraph foi introduzido na spec 002. A API já estava implementada e testada em Node.js. `better-sqlite3` síncrono sem driver externo é exclusivo do ecossistema Node.

### Alternativa B: Deno + Oak / Bun + Elysia
**Por que não**: Runtimes mais novos, ecossistema menos maduro. Node.js 20 LTS tem suporte garantido até 2026, comunidade massiva e compatibilidade com Docker.

### Alternativa C: Java + Spring Boot
**Por que não**: Overhead desproporcional para um MVP — JVM, build tools, tempo de inicialização. Node.js + Express sobe em <1s.

## Consequências

### Aceitas
- **Ecossistema maduro**: Express é o framework web mais usado no Node.js — documentação farta, middleware pronto (rate-limit, cors, morgan).
- **Single-threaded event loop**: adequado para I/O bound (chamadas SQLite, cache). Sem complexidade de thread pool.
- **Inicialização rápida**: container sobe em <2s.
- **Testes isolados**: `jest` com `:memory:` SQLite — cada suite de teste tem banco limpo.

### Trade-offs
- **Síncrono por padrão**: `better-sqlite3` é síncrono — bloqueia o event loop durante queries. Aceitável para SQLite local com queries <1ms.
- **Sem TypeScript**: JavaScript puro. TypeScript seria desejável em produção para type-safety, mas adiciona step de build.

### Condições que invalidam
1. Escala horizontal necessária → SQLite single-node não escala; migrar para PostgreSQL + pool de conexões.
2. Time padroniza TypeScript → migrar para `ts-node` ou `tsx`.

## Referências

- `api/package.json` — dependências
- `api/src/app.js` — factory `createApp(db)` com Express
- `api/src/server.js` — inicialização e seed condicional
