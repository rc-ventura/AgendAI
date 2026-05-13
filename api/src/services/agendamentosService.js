const cache = require('../cache');

function createAgendamentosService(db, { agendamentosRepo, pacientesRepo, horariosRepo }) {
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

  function criarAgendamento(pacienteEmail, horarioId) {
    const paciente = pacientesRepo.findByEmail(pacienteEmail);
    if (!paciente) {
      const error = new Error('Paciente não encontrado');
      error.statusCode = 404;
      throw error;
    }

    // Atomic reservation: UPDATE only succeeds when disponivel=1, preventing race conditions
    const transaction = db.transaction(() => {
      const claimed = horariosRepo.claimIfAvailable(horarioId);
      if (!claimed || claimed.changes === 0) {
        const error = new Error('Horário não está mais disponível');
        error.statusCode = 409;
        throw error;
      }
      const result = agendamentosRepo.create(paciente.id, horarioId);
      cache.delByPrefix('horarios');
      return agendamentosRepo.findById(result.lastInsertRowid);
    });

    const row = transaction();
    return formatAgendamento(row);
  }

  function buscarAgendamento(id) {
    const row = agendamentosRepo.findById(id);
    if (!row) {
      const error = new Error('Agendamento não encontrado');
      error.statusCode = 404;
      throw error;
    }
    return formatAgendamento(row);
  }

  function cancelarAgendamento(id) {
    const agendamento = agendamentosRepo.findByIdWithStatus(id);
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

    const transaction = db.transaction(() => {
      agendamentosRepo.updateStatus(id, 'cancelado');
      horariosRepo.updateDisponivel(agendamento.horario_id, 1);
      cache.delByPrefix('horarios');
      return agendamentosRepo.findById(id);
    });

    const row = transaction();
    return formatAgendamento(row);
  }

  return { criarAgendamento, buscarAgendamento, cancelarAgendamento };
}

module.exports = { createAgendamentosService };
