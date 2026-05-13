const { getDb } = require('./db/connection');
const { seed } = require('./db/seed');
const { createApp } = require('./app');

const db = getDb();
seed(db);

const app = createApp(db);
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(`AgendAI API running on port ${PORT}`);
});
