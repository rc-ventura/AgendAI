const { isValidDate } = require('../middlewares/validation');

function createHorariosController({ horariosService }) {
  async function listarDisponiveis(req, res, next) {
    try {
      const { data } = req.query;
      if (data !== undefined && !isValidDate(data)) {
        return res.status(400).json({ error: 'Data inválida. Use formato YYYY-MM-DD' });
      }
      const result = horariosService.listarDisponiveis(data);
      res.json(result);
    } catch (err) {
      next(err);
    }
  }

  return { listarDisponiveis };
}

module.exports = { createHorariosController };
