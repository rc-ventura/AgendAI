const express = require('express');
const router = express.Router();

const { createPainelRepository } = require('../repositories/painelRepository');
const { createPainelService } = require('../services/painelService');
const { createPainelController } = require('../controllers/painelController');

function painelRouter(db) {
  const painelRepo = createPainelRepository(db);
  const painelService = createPainelService({ painelRepo });
  const controller = createPainelController({ painelService });

  router.get('/', controller.renderizar);

  return router;
}

module.exports = painelRouter;
