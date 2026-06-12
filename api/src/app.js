const express = require('express');
const rateLimit = require('express-rate-limit');
const requestId = require('./middlewares/requestId');
const requestLogger = require('./middlewares/requestLogger');
const errorHandler = require('./middlewares/errorHandler');
const horariosRouter = require('./routes/horarios');
const agendamentosRouter = require('./routes/agendamentos');
const pacientesRouter = require('./routes/pacientes');
const pagamentosRouter = require('./routes/pagamentos');
const painelRouter = require('./routes/painel');

// Rate limiter: max 100 requests per 15-minute window per IP
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Muitas requisições. Tente novamente em instantes.' },
});

function createApp(pool) {
  const app = express();

  app.use(requestId);
  app.use(express.json());
  // Request timeout: abort connections that hang for more than 30s
  app.use((req, res, next) => {
    res.setTimeout(30000, () => {
      res.status(503).json({ error: 'Tempo de requisição excedido' });
    });
    next();
  });
  // Skip rate limiting in test env to prevent shared-counter leaks across test apps
  if (process.env.NODE_ENV !== 'test') {
    app.use(limiter);
  }
  app.use(requestLogger);

  app.use('/horarios', horariosRouter(pool));
  app.use('/agendamentos', agendamentosRouter(pool));
  app.use('/pacientes', pacientesRouter(pool));
  app.use('/pagamentos', pagamentosRouter(pool));
  app.use('/painel', painelRouter(pool));

  app.use(errorHandler);

  return app;
}

module.exports = { createApp };
