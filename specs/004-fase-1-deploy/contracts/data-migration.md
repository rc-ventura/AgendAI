# Contract: `better-sqlite3` → `pg` Migration (per-layer rules)

**Feature**: [../spec.md](../spec.md) · **Decisions**: [../research.md](../research.md)
(D3–D6) · **Model**: [../data-model.md](../data-model.md).

This is the **authoritative translation contract** for the API data-layer migration. Apply
these rules mechanically per layer. The observable HTTP contract (status codes, JSON shapes)
MUST NOT change — the 39 Jest tests are the gate.

---

## 1. Driver & API mapping

| `better-sqlite3` (sync) | `pg` (async) |
|---|---|
| `new Database(path)` | `new Pool({ connectionString, ssl })` (ssl conditional — see §2) |
| `db.prepare(sql).get(params)` | `(await exec.query(sql, params)).rows[0]` |
| `db.prepare(sql).all(params)` | `(await exec.query(sql, params)).rows` |
| `db.prepare(sql).run(params)` | `await exec.query(sql, params)` → use `.rowCount` |
| `.run().changes` | `result.rowCount` |
| `.run().lastInsertRowid` | `INSERT … RETURNING id` → `result.rows[0].id` |
| `db.transaction(fn)` | pooled client + `BEGIN`/`COMMIT`/`ROLLBACK` (see §4) |
| `?` placeholders | `$1, $2, …` (1-indexed, positional) |
| `db.exec(schemaSql)` | `await pool.query(schemaSql)` (multi-statement OK) |

`exec` = either the `pool` (autocommit) or a transaction `client`.

---

## 2. `connection.js`

```js
const { Pool } = require('pg');

// SSL must be CONDITIONAL: Neon requires TLS, but the CI `postgres:16` service and the
// local docker Postgres do not speak SSL — forcing `ssl` there makes `pg` fail to connect
// (breaks `npm test` locally and in CI). Enable SSL only for remote/managed hosts.
function needsSsl(connectionString = '') {
  if (process.env.PGSSLMODE === 'disable') return false;
  if (/sslmode=require/.test(connectionString)) return true;
  // local/CI Postgres → no SSL
  return !/@(localhost|127\.0\.0\.1|postgres)[:/]/.test(connectionString);
}

function createConnection(connectionString) {
  const pool = new Pool({
    connectionString,
    ssl: needsSsl(connectionString) ? { rejectUnauthorized: false } : false,
  });
  return pool;
}

async function initSchema(pool) {
  const schema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
  await pool.query(schema); // idempotent CREATE TABLE IF NOT EXISTS
}

let instance = null;
function getPool() {
  if (!instance) instance = createConnection(process.env.DATABASE_URL);
  return instance;
}
module.exports = { getPool, createConnection, initSchema };
```

- Keep `getPool()` (prod singleton) **and** `createConnection(connStr)` (test injection).
- Fail fast if `DATABASE_URL` is missing (FR-016).

---

## 3. Repositories — async + `$n` + executor

Each factory keeps its `create…Repository(pool)` signature; every method becomes `async`,
takes an optional `exec = pool` trailing arg, and returns `.rows` / `.rows[0]` / the result.

Representative translations:

```js
// horariosRepository
async function findAvailable(exec = pool) {
  const { rows } = await exec.query(`SELECT … WHERE h.disponivel = 1 ORDER BY h.data_hora`);
  return rows;
}
async function findAvailableByDate(data, exec = pool) {
  const { rows } = await exec.query(
    `SELECT … WHERE h.disponivel = 1 AND left(h.data_hora,10) = $1 ORDER BY h.data_hora`,
    [data]);
  return rows;
}
async function claimIfAvailable(id, exec = pool) {
  return exec.query(
    'UPDATE horarios SET disponivel = 0 WHERE id = $1 AND disponivel = 1', [id]);
}

// agendamentosRepository
async function create(pacienteId, horarioId, status = 'ativo', exec = pool) {
  return exec.query(
    'INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES ($1,$2,$3) RETURNING id',
    [pacienteId, horarioId, status]);
}
```

Rules:
- `date(h.data_hora) = ?` → `left(h.data_hora, 10) = $1`.
- `lastInsertRowid` consumers read `result.rows[0].id`.
- `claimed.changes === 0` → `claimed.rowCount === 0`.

---

## 4. Services — await + transactions

Convert each service factory's methods to `async`. Replace `db.transaction(() => …)` with a
pooled client. Pattern (create appointment):

```js
async function criarAgendamento(pacienteEmail, horarioId) {
  const paciente = await pacientesRepo.findByEmail(pacienteEmail);
  if (!paciente) { const e = new Error('Paciente não encontrado'); e.statusCode = 404; throw e; }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const claimed = await horariosRepo.claimIfAvailable(horarioId, client);
    if (claimed.rowCount === 0) { const e = new Error('Horário não está mais disponível'); e.statusCode = 409; throw e; }
    const ins = await agendamentosRepo.create(paciente.id, horarioId, 'ativo', client);
    await client.query('COMMIT');
    cache.delByPrefix('horarios');                       // after commit
    return formatAgendamento(await agendamentosRepo.findById(ins.rows[0].id));
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}
```

- The service factory must receive the `pool` (so it can `connect()`); repos still receive
  the same pool. Keep the existing DI shape `createXService(pool, { …repos })`.
- `cache.delByPrefix('horarios')` placement (post-commit) is unchanged.

---

## 5. Controllers

Already `async function`; add `await` before each service call:
`const result = await horariosService.listarDisponiveis(data);`. Error handling via
`next(err)` is unchanged.

---

## 6. `app.js` / `server.js`

```js
// app.js
function createApp(pool) { /* wire routers with pool, unchanged structure */ }

// server.js
(async () => {
  const pool = getPool();
  await initSchema(pool);
  await seed(pool);
  const app = createApp(pool);
  app.listen(process.env.PORT || 3000, () => console.log(`API on ${PORT}`));
})().catch((e) => { console.error('Startup failed', e); process.exit(1); });
```

Startup is async: **schema + seed must complete before `listen()`** (FR-007). Fail-fast on
error (FR-016).

---

## 7. `seed.js`

- `async function seed(pool)`.
- Count-guard: `const { rows } = await pool.query('SELECT count(*)::int AS n FROM medicos'); if (rows[0].n > 0) return;`
- Wrap inserts in a transaction (`BEGIN`/`COMMIT` on a client).
- Replace `lastInsertRowid` with `RETURNING id`.
- Preserve the exact seed data and the local-time `formatLocalDate` weekday logic.

---

## 8. Tests (`tests/setup.js` + `*.test.js`)

```js
// setup.js
async function resetDb(pool) {
  await pool.query('DROP TABLE IF EXISTS agendamentos, pagamentos, horarios, pacientes, medicos CASCADE');
  await initSchema(pool);
  await seed(pool);
}
async function createTestApp() {
  cache.clear();
  const pool = getTestPool();            // connects to DATABASE_URL (test DB)
  await resetDb(pool);
  return { app: createApp(pool), pool };
}
```

- Each `*.test.js`: `let app; beforeEach(async () => ({ app } = await createTestApp()));`
- Assertions and request flows stay identical.
- `jest --runInBand --forceExit` is retained; close the pool in `afterAll`.

---

## Acceptance (gate)

- `cd api && npm test` → all 39 Jest tests pass against real Postgres.
- No raw `?` placeholders, no `better-sqlite3` import, no `.prepare(`/`.get(`/`.all(`/`.run(`
  remain in `api/src`.
- `concurrency.test.js` still yields `[201, 409]`.
