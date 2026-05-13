function createHorariosRepository(db) {
  function findAvailable() {
    return db.prepare(`
      SELECT h.id, h.data_hora, h.disponivel,
             m.id as medico_id, m.nome as medico_nome, m.especialidade
      FROM horarios h
      JOIN medicos m ON m.id = h.medico_id
      WHERE h.disponivel = 1
      ORDER BY h.data_hora
    `).all();
  }

  function findAvailableByDate(data) {
    return db.prepare(`
      SELECT h.id, h.data_hora, h.disponivel,
             m.id as medico_id, m.nome as medico_nome, m.especialidade
      FROM horarios h
      JOIN medicos m ON m.id = h.medico_id
      WHERE h.disponivel = 1 AND date(h.data_hora) = ?
      ORDER BY h.data_hora
    `).all(data);
  }

  function findById(id) {
    return db.prepare('SELECT id, disponivel FROM horarios WHERE id = ?').get(id);
  }

  function updateDisponivel(id, disponivel) {
    return db.prepare('UPDATE horarios SET disponivel = ? WHERE id = ?').run(disponivel, id);
  }

  // Atomically marks a slot as unavailable only if it is currently available.
  // Returns the run-info object; check .changes === 1 to confirm success.
  function claimIfAvailable(id) {
    return db.prepare('UPDATE horarios SET disponivel = 0 WHERE id = ? AND disponivel = 1').run(id);
  }

  return { findAvailable, findAvailableByDate, findById, updateDisponivel, claimIfAvailable };
}

module.exports = { createHorariosRepository };
