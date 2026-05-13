const request = require('supertest');
const { createTestApp } = require('./setup');

let app, db;

beforeEach(() => {
  ({ app, db } = createTestApp());
});

describe('GET /horarios/disponiveis', () => {
  it('retorna array com horários disponíveis', async () => {
    const res = await request(app).get('/horarios/disponiveis');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);

    const h = res.body[0];
    expect(h).toHaveProperty('id');
    expect(h).toHaveProperty('data_hora');
    expect(h).toHaveProperty('disponivel', 1);
    expect(h).toHaveProperty('medico');
    expect(h.medico).toHaveProperty('id');
    expect(h.medico).toHaveProperty('nome');
    expect(h.medico).toHaveProperty('especialidade');
  });

  it('filtra por data quando ?data= é fornecido', async () => {
    const allRes = await request(app).get('/horarios/disponiveis');
    const firstDate = allRes.body[0].data_hora.slice(0, 10);

    const filtered = await request(app).get(`/horarios/disponiveis?data=${firstDate}`);
    expect(filtered.status).toBe(200);
    filtered.body.forEach(h => {
      expect(h.data_hora.startsWith(firstDate)).toBe(true);
    });
  });

  it('retorna [] para data sem horários', async () => {
    const res = await request(app).get('/horarios/disponiveis?data=2000-01-01');
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it('não retorna horários indisponíveis', async () => {
    const res = await request(app).get('/horarios/disponiveis');
    res.body.forEach(h => {
      expect(h.disponivel).toBe(1);
    });
  });
});
