function createAgendamentosRepository(db) {
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

  function findById(id) {
    return selectAgendamento.get(id);
  }

  function findByIdWithStatus(id) {
    return db.prepare('SELECT id, status, horario_id FROM agendamentos WHERE id = ?').get(id);
  }

  function create(pacienteId, horarioId, status = 'ativo') {
    return db.prepare(
      'INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES (?, ?, ?)'
    ).run(pacienteId, horarioId, status);
  }

  function updateStatus(id, status) {
    return db.prepare("UPDATE agendamentos SET status = ? WHERE id = ?").run(status, id);
  }

  function findByPacienteEmail(email, status = null) {
    const base = `
      SELECT a.id, a.status, a.criado_em,
             p.id as pac_id, p.nome as pac_nome, p.email as pac_email,
             h.id as hor_id, h.data_hora,
             m.nome as med_nome
      FROM agendamentos a
      JOIN pacientes p ON p.id = a.paciente_id
      JOIN horarios h ON h.id = a.horario_id
      JOIN medicos m ON m.id = h.medico_id
      WHERE p.email = ?
    `;
    if (status) {
      return db.prepare(base + ' AND a.status = ? ORDER BY h.data_hora ASC').all(email, status);
    }
    return db.prepare(base + ' ORDER BY h.data_hora ASC').all(email);
  }

  return { findById, findByIdWithStatus, create, updateStatus, findByPacienteEmail };
}

module.exports = { createAgendamentosRepository };
