const { createConnection } = require('../src/db/connection');
const { seed } = require('../src/db/seed');
const { createApp } = require('../src/app');
const cache = require('../src/cache');

function createTestDb() {
  const db = createConnection(':memory:');
  seed(db);
  return db;
}

function createTestApp() {
  // Clear the module-level cache singleton so each test app starts with a clean cache.
  // Without this, cached results from a previous test's DB would leak into the new app.
  cache.clear();
  const db = createTestDb();
  return { app: createApp(db), db };
}

module.exports = { createTestDb, createTestApp };
