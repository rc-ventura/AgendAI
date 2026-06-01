function createPagamentosService({ pagamentosRepo }) {
  async function listarPagamentos() {
    const rows = await pagamentosRepo.findAll();
    return rows.map(r => ({
      id: r.id,
      descricao: r.descricao,
      valor: Number(r.valor), // pg returns NUMERIC as string — cast to number
      formas: JSON.parse(r.formas),
    }));
  }

  return { listarPagamentos };
}

module.exports = { createPagamentosService };
