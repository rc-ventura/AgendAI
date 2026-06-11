'use strict';
const { getPool, initSchema } = require('./db/connection');
const { seed } = require('./db/seed');
const { initializeWithRetry } = require('./db/init');
const { createApp } = require('./app');

(async () => {
  if (!process.env.DATABASE_URL) {
    console.error('Startup failed: DATABASE_URL is not set');
    process.exit(1);
  }

  const pool = getPool();

  // Initialize DB with retry on transient Postgres startup delays.
  await initializeWithRetry(pool, initSchema, seed);

  const app = createApp(pool);
  const PORT = process.env.PORT || 3000;

  app.listen(PORT, () => {
    console.log(`AgendAI API running on port ${PORT}`);
  });
})().catch((err) => {
  console.error('Startup failed:', err.message);
  process.exit(1);
});
