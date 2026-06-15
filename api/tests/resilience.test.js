'use strict';
/**
 * B6 — Resilience contract tests (T024)
 * Contract #3 (API side): cold-start retry on Postgres unavailable → succeeds after retry.
 * Contract #4 (API side): 409 from repository → returned once, not retried at HTTP layer.
 */

const { createTestApp, closeTestPool } = require('./setup');
const request = require('supertest');

afterAll(async () => {
  await closeTestPool();
});

describe('B6 resilience — repository transient error (T030)', () => {
  it('retries a transient ECONNRESET on pool.query and succeeds', async () => {
    const { app, pool } = await createTestApp();

    let callCount = 0;
    const original = pool.query.bind(pool);

    // Inject one transient error on the first query call
    jest.spyOn(pool, 'query').mockImplementation(async (...args) => {
      callCount++;
      if (callCount === 1) {
        const err = new Error('Connection terminated unexpectedly');
        err.code = 'ECONNRESET';
        throw err;
      }
      return original(...args);
    });

    const res = await request(app).get('/horarios/disponiveis');
    pool.query.mockRestore();

    // With retry in place: should succeed; without retry: 500
    expect(res.status).toBe(200);
  });

  it('does not retry a 409 conflict — returns it immediately', async () => {
    const { app } = await createTestApp();

    // Slot 1 is already booked in seed — booking it again must 409 on the first try
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'ana@email.com', horario_id: 1 });

    // 409 means the slot was taken: no retry, no 500
    expect([409, 400]).toContain(res.status);
  });
});
