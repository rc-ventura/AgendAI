const { randomUUID } = require('crypto');
const pino = require('pino');

const logger = pino({
  level: process.env.NODE_ENV === 'test' ? 'silent' : 'info',
});

function requestLogger(req, res, next) {
  const start = Date.now();
  const correlationId = req.headers['x-request-id'] || randomUUID();

  req.correlationId = correlationId;
  res.setHeader('X-Request-ID', correlationId);

  res.on('finish', () => {
    logger.info({
      correlation_id: correlationId,
      method: req.method,
      path: req.path,
      status_code: res.statusCode,
      duration_ms: Date.now() - start,
    });
  });

  next();
}

module.exports = requestLogger;
