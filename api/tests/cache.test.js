const request = require('supertest');
const { createTestApp } = require('./setup');
const cache = require('../src/cache');

beforeEach(() => {
  cache.clear();
});

describe('Cache de horários disponíveis', () => {
  it('segunda requisição é servida do cache (mesmo body)', async () => {
    const { app } = createTestApp();

    const res1 = await request(app).get('/horarios/disponiveis');
    const res2 = await request(app).get('/horarios/disponiveis');

    expect(res1.status).toBe(200);
    expect(res2.status).toBe(200);
    expect(res2.body).toEqual(res1.body);
  });

  it('cache é invalidado após agendamento — horário some da lista', async () => {
    const { app } = createTestApp();

    // Prime the cache
    const before = await request(app).get('/horarios/disponiveis');
    const horario = before.body[0];

    // Create appointment (should bust cache)
    await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'pedro@email.com', horario_id: horario.id });

    const after = await request(app).get('/horarios/disponiveis');
    const ids = after.body.map(h => h.id);
    expect(ids).not.toContain(horario.id);
  });

  it('cache é invalidado após cancelamento — horário volta à lista', async () => {
    const { app, db } = createTestApp();

    const agendamento = db.prepare("SELECT id, horario_id FROM agendamentos WHERE status='ativo' LIMIT 1").get();

    // Prime cache (horario should not be in list)
    const before = await request(app).get('/horarios/disponiveis');
    const idsBefore = before.body.map(h => h.id);
    expect(idsBefore).not.toContain(agendamento.horario_id);

    // Cancel (should bust cache)
    await request(app).patch(`/agendamentos/${agendamento.id}/cancelar`);

    const after = await request(app).get('/horarios/disponiveis');
    const idsAfter = after.body.map(h => h.id);
    expect(idsAfter).toContain(agendamento.horario_id);
  });
});
