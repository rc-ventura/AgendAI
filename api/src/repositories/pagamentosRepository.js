function createPagamentosRepository(db) {
  function findAll() {
    return db.prepare('SELECT id, descricao, valor, formas FROM pagamentos').all();
  }

  return { findAll };
}

module.exports = { createPagamentosRepository };
