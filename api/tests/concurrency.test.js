const request = require('supertest');
const { createTestApp } = require('./setup');

let pool;

afterAll(async () => {
  if (pool) await pool.end();
});

// Postgres row-level locking serialises competing UPDATE … WHERE disponivel=1 on the same
// slot. This validates that the atomic claimIfAvailable guard prevents double-booking even
// when two requests are fired concurrently from the same Node.js event loop.
describe('Concorrência — agendamento simultâneo do mesmo horário', () => {
  it('apenas um agendamento deve ser criado quando dois pacientes disputam o mesmo horário', async () => {
    const { app, pool: p } = await createTestApp();
    pool = p;

    const horariosRes = await request(app).get('/horarios/disponiveis');
    const horario = horariosRes.body[0];

    const [res1, res2] = await Promise.all([
      request(app)
        .post('/agendamentos')
        .send({ paciente_email: 'joao@email.com', horario_id: horario.id }),
      request(app)
        .post('/agendamentos')
        .send({ paciente_email: 'maria@email.com', horario_id: horario.id }),
    ]);

    const statuses = [res1.status, res2.status].sort();
    // Exactly one 201 and one 409
    expect(statuses).toEqual([201, 409]);
  });
});
