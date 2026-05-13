function createPagamentosService({ pagamentosRepo }) {
  function listarPagamentos() {
    const rows = pagamentosRepo.findAll();
    return rows.map(r => ({
      id: r.id,
      descricao: r.descricao,
      valor: r.valor,
      formas: JSON.parse(r.formas),
    }));
  }

  return { listarPagamentos };
}

module.exports = { createPagamentosService };
