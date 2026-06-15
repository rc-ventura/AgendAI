const { createConnection, initSchema } = require('../src/db/connection');
const { seed } = require('../src/db/seed');
const { createApp } = require('../src/app');
const cache = require('../src/cache');

// Module-level singleton pool. Each test file creates exactly ONE pg.Pool that is
// reused across its `beforeEach` resets (which only drop+seed data, not the pool)
// and closed once in `afterAll` via closeTestPool(). Without this, every
// createTestApp() call would build a new Pool and leak its connections — quickly
// exhausting Postgres `max_connections` under --runInBand across all test files.
let _testPool = null;

function getTestPool() {
  if (!_testPool) {
    const connStr = process.env.DATABASE_URL;
    if (!connStr) throw new Error('DATABASE_URL must be set for tests');
    _testPool = createConnection(connStr);
  }
  return _testPool;
}

async function closeTestPool() {
  if (_testPool) {
    const p = _testPool;
    _testPool = null;
    await p.end();
  }
}

// Drop all tables and recreate schema + seed — called in beforeEach to guarantee isolation.
async function resetDb(pool) {
  await pool.query(`
    DROP TABLE IF EXISTS agendamentos, pagamentos, horarios, pacientes, medicos CASCADE
  `);
  await initSchema(pool);
  await seed(pool);
}

async function createTestApp() {
  await cache.clear();
  const pool = getTestPool();
  await resetDb(pool);
  return { app: createApp(pool), pool };
}

module.exports = { createTestApp, resetDb, getTestPool, closeTestPool };
