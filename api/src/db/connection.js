const { Pool } = require('pg');
const path = require('path');
const fs = require('fs');

// SSL must be CONDITIONAL: managed Postgres (Neon) requires TLS, but the local docker
// Postgres and the CI `postgres:16` service do not speak SSL — forcing `ssl` there makes
// `pg` fail to connect. Enable SSL only for remote/managed hosts.
function needsSsl(connectionString = '') {
  if (process.env.PGSSLMODE === 'disable') return false;
  if (/sslmode=require/.test(connectionString)) return true;
  // local/CI Postgres → no SSL
  return !/@(localhost|127\.0\.0\.1|postgres)[:/]/.test(connectionString);
}

function createConnection(connectionString) {
  if (!connectionString) {
    throw new Error('DATABASE_URL is not set — cannot connect to Postgres');
  }
  return new Pool({
    connectionString,
    ssl: needsSsl(connectionString) ? { rejectUnauthorized: false } : false,
  });
}

// Runs the idempotent schema (CREATE TABLE IF NOT EXISTS) — safe on every startup.
async function initSchema(pool) {
  const schemaPath = path.join(__dirname, 'schema.sql');
  const schema = fs.readFileSync(schemaPath, 'utf8');
  await pool.query(schema);
}

let instance = null;

function getPool() {
  if (!instance) {
    instance = createConnection(process.env.DATABASE_URL);
  }
  return instance;
}

module.exports = { getPool, createConnection, initSchema };
