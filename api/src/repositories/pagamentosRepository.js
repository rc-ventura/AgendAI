function createPagamentosRepository(pool) {
  async function findAll(exec = pool) {
    const { rows } = await exec.query('SELECT id, descricao, valor, formas FROM pagamentos');
    return rows;
  }

  return { findAll };
}

module.exports = { createPagamentosRepository };
