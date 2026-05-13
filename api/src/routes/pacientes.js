const express = require('express');

const { createPacientesRepository } = require('../repositories/pacientesRepository');
const { createPacientesService } = require('../services/pacientesService');
const { createPacientesController } = require('../controllers/pacientesController');

function pacientesRouter(db) {
  const router = express.Router();

  const pacientesRepo = createPacientesRepository(db);
  const pacientesService = createPacientesService({ pacientesRepo });
  const controller = createPacientesController({ pacientesService });

  router.get('/:email', controller.buscarPorEmail);

  return router;
}

module.exports = pacientesRouter;
