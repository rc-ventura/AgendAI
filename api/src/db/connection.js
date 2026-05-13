const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

function createConnection(dbPath) {
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  const schemaPath = path.join(__dirname, 'schema.sql');
  const schema = fs.readFileSync(schemaPath, 'utf8');
  db.exec(schema);

  return db;
}

let instance = null;

function getDb() {
  if (!instance) {
    const dbPath = process.env.DB_PATH || path.join(__dirname, '../../../data/clinica.db');
    instance = createConnection(dbPath);
  }
  return instance;
}

module.exports = { getDb, createConnection };
