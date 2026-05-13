const { isValidEmail } = require('../middlewares/validation');

function createPacientesController({ pacientesService }) {
  async function buscarPorEmail(req, res, next) {
    try {
      if (!isValidEmail(req.params.email)) {
        return res.status(400).json({ error: 'E-mail inválido' });
      }
      const result = pacientesService.buscarPorEmail(req.params.email);
      res.json(result);
    } catch (err) {
      next(err);
    }
  }

  return { buscarPorEmail };
}

module.exports = { createPacientesController };
