const express = require('express');
const router = express.Router();
const cache = require('../cache');

function horariosRouter(db) {
  router.get('/disponiveis', (req, res, next) => {
    try {
      const { data } = req.query;
      const cacheKey = data ? `horarios:${data}` : 'horarios';

      const cached = cache.get(cacheKey);
      if (cached) return res.json(cached);

      let rows;
      if (data) {
        rows = db.prepare(`
          SELECT h.id, h.data_hora, h.disponivel,
                 m.id as medico_id, m.nome as medico_nome, m.especialidade
          FROM horarios h
          JOIN medicos m ON m.id = h.medico_id
          WHERE h.disponivel = 1 AND date(h.data_hora) = ?
          ORDER BY h.data_hora
        `).all(data);
      } else {
        rows = db.prepare(`
          SELECT h.id, h.data_hora, h.disponivel,
                 m.id as medico_id, m.nome as medico_nome, m.especialidade
          FROM horarios h
          JOIN medicos m ON m.id = h.medico_id
          WHERE h.disponivel = 1
          ORDER BY h.data_hora
        `).all();
      }

      const result = rows.map(r => ({
        id: r.id,
        data_hora: r.data_hora,
        disponivel: r.disponivel,
        medico: {
          id: r.medico_id,
          nome: r.medico_nome,
          especialidade: r.especialidade,
        },
      }));

      cache.set(cacheKey, result);
      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = horariosRouter;
