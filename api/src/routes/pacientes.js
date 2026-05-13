const express = require('express');
const router = express.Router();

function pacientesRouter(db) {
  router.get('/:email', (req, res, next) => {
    try {
      const { email } = req.params;
      const paciente = db.prepare('SELECT id, nome, email, telefone FROM pacientes WHERE email = ?').get(email);
      if (!paciente) {
        return res.status(404).json({ error: 'Paciente não encontrado' });
      }
      res.json(paciente);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = pacientesRouter;
