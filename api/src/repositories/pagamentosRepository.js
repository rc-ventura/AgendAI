'use strict';
const { withDbRetry } = require('../db/withRetry');

function createPagamentosRepository(pool) {
  async function findAll(exec = pool) {
    const { rows } = await withDbRetry(() => exec.query(
      'SELECT id, descricao, valor, formas FROM pagamentos'
    ));
    return rows;
  }

  return { findAll };
}

module.exports = { createPagamentosRepository };
