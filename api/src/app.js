const express = require('express');
const rateLimit = require('express-rate-limit');
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

function createApp(db) {
  const app = express();

  app.use(express.json());
  // Request timeout: abort connections that hang for more than 30s
  app.use((req, res, next) => {
    res.setTimeout(30000, () => {
      res.status(503).json({ error: 'Tempo de requisição excedido' });
    });
    next();
  });
  app.use(limiter);
  app.use(requestLogger);

  app.use('/horarios', horariosRouter(db));
  app.use('/agendamentos', agendamentosRouter(db));
  app.use('/pacientes', pacientesRouter(db));
  app.use('/pagamentos', pagamentosRouter(db));
  app.use('/painel', painelRouter(db));

  app.use(errorHandler);

  return app;
}

module.exports = { createApp };
