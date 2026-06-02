const { getPool, initSchema } = require('./db/connection');
const { seed } = require('./db/seed');
const { createApp } = require('./app');

(async () => {
  const pool = getPool();
  await initSchema(pool);
  await seed(pool);

  const app = createApp(pool);
  const PORT = process.env.PORT || 3000;

  app.listen(PORT, () => {
    console.log(`AgendAI API running on port ${PORT}`);
  });
})().catch((err) => {
  console.error('Startup failed:', err.message);
  process.exit(1);
});
