const cache = require('../cache');

function createAgendamentosService(pool, { agendamentosRepo, pacientesRepo, horariosRepo }) {
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

  async function criarAgendamento(pacienteEmail, horarioId) {
    const paciente = await pacientesRepo.findByEmail(pacienteEmail);
    if (!paciente) {
      const error = new Error('Paciente não encontrado');
      error.statusCode = 404;
      throw error;
    }

    const client = await pool.connect();
    let newId;
    try {
      await client.query('BEGIN');

      // Atomic reservation: UPDATE only succeeds when disponivel=1, preventing race conditions
      const claimed = await horariosRepo.claimIfAvailable(horarioId, client);
      if (claimed.rowCount === 0) {
        const error = new Error('Horário não está mais disponível');
        error.statusCode = 409;
        throw error;
      }

      const ins = await agendamentosRepo.create(paciente.id, horarioId, 'ativo', client);
      await client.query('COMMIT');
      newId = ins.rows[0].id;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }

    // Post-commit work runs on the pool (autocommit), not the txn client, so it
    // must sit outside the try/catch — otherwise a throw here would trigger a
    // ROLLBACK on an already-committed transaction.
    cache.delByPrefix('horarios');
    const row = await agendamentosRepo.findById(newId);
    return formatAgendamento(row);
  }

  async function buscarAgendamento(id) {
    const row = await agendamentosRepo.findById(id);
    if (!row) {
      const error = new Error('Agendamento não encontrado');
      error.statusCode = 404;
      throw error;
    }
    return formatAgendamento(row);
  }

  async function cancelarAgendamento(id) {
    const agendamento = await agendamentosRepo.findByIdWithStatus(id);
    if (!agendamento) {
      const error = new Error('Agendamento não encontrado');
      error.statusCode = 404;
      throw error;
    }
    if (agendamento.status === 'cancelado') {
      const error = new Error('Agendamento já está cancelado');
      error.statusCode = 400;
      throw error;
    }

    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      await agendamentosRepo.updateStatus(id, 'cancelado', client);
      await horariosRepo.updateDisponivel(agendamento.horario_id, 1, client);
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }

    // Post-commit: see note in criarAgendamento.
    cache.delByPrefix('horarios');
    const row = await agendamentosRepo.findById(id);
    return formatAgendamento(row);
  }

  async function listarAgendamentosPaciente(email, status = null) {
    const rows = await agendamentosRepo.findByPacienteEmail(email, status);
    return rows.map(formatAgendamento);
  }

  return { criarAgendamento, buscarAgendamento, cancelarAgendamento, listarAgendamentosPaciente };
}

module.exports = { createAgendamentosService };
