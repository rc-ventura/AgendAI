const express = require('express');
const router = express.Router();
const cache = require('../cache');

function agendamentosRouter(db) {
  const selectAgendamento = db.prepare(`
    SELECT a.id, a.status, a.criado_em,
           p.id as pac_id, p.nome as pac_nome, p.email as pac_email,
           h.id as hor_id, h.data_hora,
           m.nome as med_nome
    FROM agendamentos a
    JOIN pacientes p ON p.id = a.paciente_id
    JOIN horarios h ON h.id = a.horario_id
    JOIN medicos m ON m.id = h.medico_id
    WHERE a.id = ?
  `);

  function formatAgendamento(row) {
    return {
      id: row.id,
      paciente: { id: row.pac_id, nome: row.pac_nome, email: row.pac_email },
      horario: { id: row.hor_id, data_hora: row.data_hora },
      medico: { nome: row.med_nome },
      status: row.status,
      criado_em: row.criado_em,
    };
  }

  router.post('/', (req, res, next) => {
    try {
      const { paciente_email, horario_id } = req.body;

      const paciente = db.prepare('SELECT id FROM pacientes WHERE email = ?').get(paciente_email);
      if (!paciente) {
        return res.status(404).json({ error: 'Paciente não encontrado' });
      }

      const horario = db.prepare('SELECT id, disponivel FROM horarios WHERE id = ?').get(horario_id);
      if (!horario || horario.disponivel !== 1) {
        return res.status(409).json({ error: 'Horário não está mais disponível' });
      }

      const criar = db.transaction(() => {
        const result = db.prepare(
          'INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES (?, ?, ?)'
        ).run(paciente.id, horario_id, 'ativo');

        db.prepare('UPDATE horarios SET disponivel=0 WHERE id=?').run(horario_id);

        cache.delByPrefix('horarios');

        return selectAgendamento.get(result.lastInsertRowid);
      });

      const row = criar();
      res.status(201).json(formatAgendamento(row));
    } catch (err) {
      next(err);
    }
  });

  router.get('/:id', (req, res, next) => {
    try {
      const row = selectAgendamento.get(req.params.id);
      if (!row) {
        return res.status(404).json({ error: 'Agendamento não encontrado' });
      }
      res.json(formatAgendamento(row));
    } catch (err) {
      next(err);
    }
  });

  router.patch('/:id/cancelar', (req, res, next) => {
    try {
      const agendamento = db.prepare('SELECT id, status, horario_id FROM agendamentos WHERE id = ?').get(req.params.id);
      if (!agendamento) {
        return res.status(404).json({ error: 'Agendamento não encontrado' });
      }
      if (agendamento.status === 'cancelado') {
        return res.status(400).json({ error: 'Agendamento já está cancelado' });
      }

      const cancelar = db.transaction(() => {
        db.prepare("UPDATE agendamentos SET status='cancelado' WHERE id=?").run(agendamento.id);
        db.prepare('UPDATE horarios SET disponivel=1 WHERE id=?').run(agendamento.horario_id);
        cache.delByPrefix('horarios');
      });

      cancelar();
      res.json({ id: agendamento.id, status: 'cancelado' });
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = agendamentosRouter;
