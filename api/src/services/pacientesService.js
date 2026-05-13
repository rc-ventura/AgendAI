function createPacientesService({ pacientesRepo }) {
  function buscarPorEmail(email) {
    const paciente = pacientesRepo.findByEmail(email);
    if (!paciente) {
      const error = new Error('Paciente não encontrado');
      error.statusCode = 404;
      throw error;
    }
    return paciente;
  }

  return { buscarPorEmail };
}

module.exports = { createPacientesService };
