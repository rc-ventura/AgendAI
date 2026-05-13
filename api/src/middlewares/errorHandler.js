function errorHandler(err, req, res, next) {
  const status = err.status || 500;
  const message = status === 500 ? 'Erro interno do servidor' : err.message;
  res.status(status).json({ error: message });
}

module.exports = errorHandler;
