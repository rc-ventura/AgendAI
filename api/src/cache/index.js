'use strict';
// B4 (ADR-025): migrado de node-cache (in-memory, per-container) para Redis.
// Quando REDIS_URI não está definido (testes, dev sem Docker), todas as
// operações são no-op — o serviço funciona sem cache, sem erro.

const DEFAULT_TTL = 60; // seconds
const PREFIX = 'agendai:cache:';

let _client; // undefined = não inicializado; null = sem Redis

function _getClient() {
  if (_client !== undefined) return _client;
  const uri = process.env.REDIS_URI;
  if (!uri) {
    _client = null;
    return null;
  }
  const Redis = require('ioredis');
  _client = new Redis(uri, { maxRetriesPerRequest: 2 });
  _client.on('error', (err) =>
    console.warn('[cache] Redis error:', err.message)
  );
  return _client;
}

async function get(key) {
  const c = _getClient();
  if (!c) return undefined;
  try {
    const raw = await c.get(PREFIX + key);
    return raw ? JSON.parse(raw) : undefined;
  } catch {
    return undefined;
  }
}

async function set(key, value, ttl = DEFAULT_TTL) {
  const c = _getClient();
  if (!c) return;
  try {
    await c.set(PREFIX + key, JSON.stringify(value), 'EX', ttl);
  } catch {
    // cache failure is non-fatal
  }
}

async function del(key) {
  const c = _getClient();
  if (!c) return;
  try {
    await c.del(PREFIX + key);
  } catch {}
}

async function delByPrefix(prefix) {
  const c = _getClient();
  if (!c) return;
  try {
    const pattern = PREFIX + prefix + '*';
    let cursor = '0';
    const keys = [];
    do {
      const [next, batch] = await c.scan(cursor, 'MATCH', pattern, 'COUNT', 100);
      cursor = next;
      keys.push(...batch);
    } while (cursor !== '0');
    if (keys.length) await c.del(...keys);
  } catch {}
}

async function clear() {
  const c = _getClient();
  if (!c) return;
  try {
    const pattern = PREFIX + '*';
    let cursor = '0';
    const keys = [];
    do {
      const [next, batch] = await c.scan(cursor, 'MATCH', pattern, 'COUNT', 100);
      cursor = next;
      keys.push(...batch);
    } while (cursor !== '0');
    if (keys.length) await c.del(...keys);
  } catch {}
}

async function quit() {
  if (_client) {
    const c = _client;
    _client = undefined;
    try { await c.quit(); } catch {}
  }
}

module.exports = { get, set, del, delByPrefix, clear, quit };
