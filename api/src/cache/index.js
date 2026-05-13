const NodeCache = require('node-cache');

const cache = new NodeCache({ stdTTL: 60, checkperiod: 30 });

function get(key) {
  return cache.get(key);
}

function set(key, value, ttl) {
  if (ttl !== undefined) {
    cache.set(key, value, ttl);
  } else {
    cache.set(key, value);
  }
}

function del(key) {
  cache.del(key);
}

function delByPrefix(prefix) {
  const keys = cache.keys().filter(k => k.startsWith(prefix));
  cache.del(keys);
}

function clear() {
  cache.flushAll();
}

module.exports = { get, set, del, delByPrefix, clear };
