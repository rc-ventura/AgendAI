const logger = require('../logger');

function errorHandler(err, req, res, next) {
  const status = err.statusCode || err.status || 500;
  if (status >= 500) {
    logger.error({
      request_id: req.requestId,
      service: 'api',
      event: 'http.error',
      status_code: status,
      err: err.message,
    });
  }
  const message = status === 500 ? 'Erro interno do servidor' : err.message;
  res.status(status).json({ error: message });
}

module.exports = errorHandler;
