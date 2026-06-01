const { createConnection, initSchema } = require('../src/db/connection');
const { seed } = require('../src/db/seed');
const { createApp } = require('../src/app');
const cache = require('../src/cache');

function getTestPool() {
  const connStr = process.env.DATABASE_URL;
  if (!connStr) throw new Error('DATABASE_URL must be set for tests');
  return createConnection(connStr);
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
  cache.clear();
  const pool = getTestPool();
  await resetDb(pool);
  return { app: createApp(pool), pool };
}

module.exports = { createTestApp, resetDb, getTestPool };
