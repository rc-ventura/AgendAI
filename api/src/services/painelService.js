function createPainelService({ painelRepo }) {
  async function listarAgendamentos() {
    return painelRepo.findAllAgendamentos();
  }

  return { listarAgendamentos };
}

module.exports = { createPainelService };
