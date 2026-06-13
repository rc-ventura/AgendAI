const pino = require('pino');

module.exports = pino({
  level: process.env.NODE_ENV === 'test' ? 'silent' : 'info',
});
