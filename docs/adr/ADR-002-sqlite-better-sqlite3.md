# ADR-002: Banco SQLite via `better-sqlite3` síncrono

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/)
**Código**: `api/src/db/connection.js`, `api/src/db/schema.sql`, `api/src/db/seed.js`

---

## Contexto

A API REST precisa de um banco de dados para médicos, pacientes, horários, agendamentos e pagamentos. O sistema é single-node, sem requisitos de concorrência entre múltiplos servidores, com volume de dados de demonstração (~3 médicos, 5 pacientes, 10 horários).

## Decisão

Usar **SQLite** via **`better-sqlite3`** — driver síncrono, sem dependência externa, arquivo único. Schema criado via DDL em `schema.sql`, seed populado condicionalmente em `seed.js` se o banco estiver vazio.

## Alternativas consideradas

### Alternativa A: PostgreSQL
**Por que não**: Exige serviço extra no Docker Compose, migrations, connection pool. Overkill para MVP single-node com 5 tabelas e dados de demo.

### Alternativa B: `sqlite3` (driver assíncrono)
**Por que não**: API de callback é verbosa. `better-sqlite3` é síncrono e 2-5x mais rápido para queries simples — ideal para o perfil de carga do MVP.

### Alternativa C: MongoDB ou outro NoSQL
**Por que não**: Dados são relacionais (agendamento → paciente, agendamento → horário, horário → médico). SQL é a ferramenta natural.

## Consequências

### Aceitas
- **Zero dependência externa**: SQLite é embutido no processo Node.js. Sem serviço de banco separado.
- **Arquivo único**: `clinica.db` no volume `./data` — backup é copiar o arquivo.
- **Seed automático**: API sobe e popula dados de demo se o banco estiver vazio.
- **Testes com `:memory:`**: cada suite Jest usa banco em memória isolado.

### Trade-offs
- **Single-writer**: SQLite serializa writes. Para carga de demo (<10 usuários), irrelevante.
- **Sem replicação**: single-node por definição. Migrar para PostgreSQL se precisar de read replicas.
- **Síncrono bloqueia event loop**: queries complexas (>100ms) congestionariam o servidor. Para queries simples (<1ms), imperceptível.

### Condições que invalidam
1. Escala horizontal → PostgreSQL com connection pooling.
2. Múltiplos servidores escrevendo → SQLite não suporta acesso concorrente de rede.
3. Volume de dados >1GB → SQLite degrada; migrar para PostgreSQL.

## Referências

- `api/src/db/connection.js` — singleton `getDb()`
- `api/src/db/schema.sql` — DDL das 5 tabelas
- `api/src/db/seed.js` — dados de demonstração
