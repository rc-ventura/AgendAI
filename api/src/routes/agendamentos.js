const express = require('express');
const router = express.Router();

const { createAgendamentosRepository } = require('../repositories/agendamentosRepository');
const { createPacientesRepository } = require('../repositories/pacientesRepository');
const { createHorariosRepository } = require('../repositories/horariosRepository');
const { createAgendamentosService } = require('../services/agendamentosService');
const { createAgendamentosController } = require('../controllers/agendamentosController');

function agendamentosRouter(db) {
  const agendamentosRepo = createAgendamentosRepository(db);
  const pacientesRepo = createPacientesRepository(db);
  const horariosRepo = createHorariosRepository(db);
  const agendamentosService = createAgendamentosService(db, { agendamentosRepo, pacientesRepo, horariosRepo });
  const controller = createAgendamentosController({ agendamentosService });

  router.post('/', controller.criar);
  router.get('/:id', controller.buscar);
  router.patch('/:id/cancelar', controller.cancelar);

  return router;
}

module.exports = agendamentosRouter;
