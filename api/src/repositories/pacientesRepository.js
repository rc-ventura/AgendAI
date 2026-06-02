function createPacientesRepository(pool) {
  async function findByEmail(email, exec = pool) {
    const { rows } = await exec.query(
      'SELECT id, nome, email, telefone FROM pacientes WHERE email = $1', [email]
    );
    return rows[0];
  }

  async function findById(id, exec = pool) {
    const { rows } = await exec.query(
      'SELECT id, nome, email, telefone FROM pacientes WHERE id = $1', [id]
    );
    return rows[0];
  }

  return { findByEmail, findById };
}

module.exports = { createPacientesRepository };
