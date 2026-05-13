const express = require('express');
const router = express.Router();

function pagamentosRouter(db) {
  router.get('/', (req, res, next) => {
    try {
      const rows = db.prepare('SELECT id, descricao, valor, formas FROM pagamentos').all();
      const result = rows.map(r => ({
        id: r.id,
        descricao: r.descricao,
        valor: r.valor,
        formas: JSON.parse(r.formas),
      }));
      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = pagamentosRouter;
