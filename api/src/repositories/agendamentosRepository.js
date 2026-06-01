function createAgendamentosRepository(pool) {
  const SELECT_AGENDAMENTO = `
    SELECT a.id, a.status, a.criado_em,
           p.id as pac_id, p.nome as pac_nome, p.email as pac_email,
           h.id as hor_id, h.data_hora,
           m.nome as med_nome
    FROM agendamentos a
    JOIN pacientes p ON p.id = a.paciente_id
    JOIN horarios h ON h.id = a.horario_id
    JOIN medicos m ON m.id = h.medico_id
    WHERE a.id = $1
  `;

  async function findById(id, exec = pool) {
    const { rows } = await exec.query(SELECT_AGENDAMENTO, [id]);
    return rows[0];
  }

  async function findByIdWithStatus(id, exec = pool) {
    const { rows } = await exec.query(
      'SELECT id, status, horario_id FROM agendamentos WHERE id = $1', [id]
    );
    return rows[0];
  }

  async function create(pacienteId, horarioId, status = 'ativo', exec = pool) {
    return exec.query(
      'INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES ($1, $2, $3) RETURNING id',
      [pacienteId, horarioId, status]
    );
  }

  async function updateStatus(id, status, exec = pool) {
    return exec.query('UPDATE agendamentos SET status = $1 WHERE id = $2', [status, id]);
  }

  async function findByPacienteEmail(email, status = null, exec = pool) {
    const base = `
      SELECT a.id, a.status, a.criado_em,
             p.id as pac_id, p.nome as pac_nome, p.email as pac_email,
             h.id as hor_id, h.data_hora,
             m.nome as med_nome
      FROM agendamentos a
      JOIN pacientes p ON p.id = a.paciente_id
      JOIN horarios h ON h.id = a.horario_id
      JOIN medicos m ON m.id = h.medico_id
      WHERE p.email = $1
    `;
    if (status) {
      const { rows } = await exec.query(base + ' AND a.status = $2 ORDER BY h.data_hora ASC', [email, status]);
      return rows;
    }
    const { rows } = await exec.query(base + ' ORDER BY h.data_hora ASC', [email]);
    return rows;
  }

  return { findById, findByIdWithStatus, create, updateStatus, findByPacienteEmail };
}

module.exports = { createAgendamentosRepository };
