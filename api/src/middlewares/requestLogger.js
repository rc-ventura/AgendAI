const pino = require('pino');

const logger = pino({
  level: process.env.NODE_ENV === 'test' ? 'silent' : 'info',
});

function requestLogger(req, res, next) {
  const start = Date.now();

  res.on('finish', () => {
    logger.info({
      request_id: req.requestId,
      service: 'api',
      event: 'http.request',
      method: req.method,
      path: req.path,
      status_code: res.statusCode,
      duration_ms: Date.now() - start,
    });
  });

  next();
}

module.exports = requestLogger;
