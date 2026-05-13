function createPainelRepository(db) {
  function findAllAgendamentos() {
    return db.prepare(`
      SELECT a.id, a.status, a.criado_em,
             p.nome as paciente_nome, p.email as paciente_email,
             m.nome as medico_nome, m.especialidade,
             h.data_hora
      FROM agendamentos a
      JOIN pacientes p ON p.id = a.paciente_id
      JOIN horarios h ON h.id = a.horario_id
      JOIN medicos m ON m.id = h.medico_id
      ORDER BY h.data_hora
    `).all();
  }

  return { findAllAgendamentos };
}

module.exports = { createPainelRepository };
