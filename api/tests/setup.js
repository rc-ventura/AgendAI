const { createConnection } = require('../src/db/connection');
const { seed } = require('../src/db/seed');
const { createApp } = require('../src/app');

function createTestDb() {
  const db = createConnection(':memory:');
  seed(db);
  return db;
}

function createTestApp() {
  const db = createTestDb();
  return { app: createApp(db), db };
}

module.exports = { createTestDb, createTestApp };
