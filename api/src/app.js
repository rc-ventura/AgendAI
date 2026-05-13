const express = require('express');
const requestLogger = require('./middlewares/requestLogger');
const errorHandler = require('./middlewares/errorHandler');
const horariosRouter = require('./routes/horarios');
const agendamentosRouter = require('./routes/agendamentos');
const pacientesRouter = require('./routes/pacientes');
const pagamentosRouter = require('./routes/pagamentos');
const painelRouter = require('./routes/painel');

function createApp(db) {
  const app = express();

  app.use(express.json());
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
