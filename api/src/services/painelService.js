function createPainelService({ painelRepo }) {
  function listarAgendamentos() {
    return painelRepo.findAllAgendamentos();
  }

  return { listarAgendamentos };
}

module.exports = { createPainelService };
