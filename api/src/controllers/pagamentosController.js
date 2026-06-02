function createPagamentosController({ pagamentosService }) {
  async function listar(req, res, next) {
    try {
      const result = await pagamentosService.listarPagamentos();
      res.json(result);
    } catch (err) {
      next(err);
    }
  }

  return { listar };
}

module.exports = { createPagamentosController };
