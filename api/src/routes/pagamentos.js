const express = require('express');

const { createPagamentosRepository } = require('../repositories/pagamentosRepository');
const { createPagamentosService } = require('../services/pagamentosService');
const { createPagamentosController } = require('../controllers/pagamentosController');

function pagamentosRouter(db) {
  const router = express.Router();

  const pagamentosRepo = createPagamentosRepository(db);
  const pagamentosService = createPagamentosService({ pagamentosRepo });
  const controller = createPagamentosController({ pagamentosService });

  router.get('/', controller.listar);

  return router;
}

module.exports = pagamentosRouter;
