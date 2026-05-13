const express = require('express');

const { createHorariosRepository } = require('../repositories/horariosRepository');
const { createHorariosService } = require('../services/horariosService');
const { createHorariosController } = require('../controllers/horariosController');

function horariosRouter(db) {
  const router = express.Router();

  const horariosRepo = createHorariosRepository(db);
  const horariosService = createHorariosService({ horariosRepo });
  const controller = createHorariosController({ horariosService });

  router.get('/disponiveis', controller.listarDisponiveis);

  return router;
}

module.exports = horariosRouter;
