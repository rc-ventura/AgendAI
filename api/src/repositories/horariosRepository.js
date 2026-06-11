'use strict';
const { withDbRetry } = require('../db/withRetry');

function createHorariosRepository(pool) {
  async function findAvailable(exec = pool) {
    const { rows } = await withDbRetry(() => exec.query(`
      SELECT h.id, h.data_hora, h.disponivel,
             m.id as medico_id, m.nome as medico_nome, m.especialidade
      FROM horarios h
      JOIN medicos m ON m.id = h.medico_id
      WHERE h.disponivel = 1
      ORDER BY h.data_hora
    `));
    return rows;
  }

  async function findAvailableByDate(data, exec = pool) {
    const { rows } = await withDbRetry(() => exec.query(`
      SELECT h.id, h.data_hora, h.disponivel,
             m.id as medico_id, m.nome as medico_nome, m.especialidade
      FROM horarios h
      JOIN medicos m ON m.id = h.medico_id
      WHERE h.disponivel = 1 AND left(h.data_hora, 10) = $1
      ORDER BY h.data_hora
    `, [data]));
    return rows;
  }

  async function findById(id, exec = pool) {
    const { rows } = await withDbRetry(() => exec.query(
      'SELECT id, disponivel FROM horarios WHERE id = $1', [id]
    ));
    return rows[0];
  }

  async function updateDisponivel(id, disponivel, exec = pool) {
    return withDbRetry(() => exec.query(
      'UPDATE horarios SET disponivel = $1 WHERE id = $2', [disponivel, id]
    ));
  }

  // Atomically marks a slot as unavailable only if it is currently available.
  // Returns the pg result; check .rowCount === 1 to confirm success.
  async function claimIfAvailable(id, exec = pool) {
    return withDbRetry(() => exec.query(
      'UPDATE horarios SET disponivel = 0 WHERE id = $1 AND disponivel = 1', [id]
    ));
  }

  return { findAvailable, findAvailableByDate, findById, updateDisponivel, claimIfAvailable };
}

module.exports = { createHorariosRepository };
