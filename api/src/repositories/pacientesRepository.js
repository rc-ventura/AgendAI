function createPacientesRepository(db) {
  function findByEmail(email) {
    return db.prepare('SELECT id, nome, email, telefone FROM pacientes WHERE email = ?').get(email);
  }

  function findById(id) {
    return db.prepare('SELECT id, nome, email, telefone FROM pacientes WHERE id = ?').get(id);
  }

  return { findByEmail, findById };
}

module.exports = { createPacientesRepository };
