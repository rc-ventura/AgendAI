const request = require('supertest');
const { createTestApp } = require('./setup');

let app, db;

beforeEach(() => {
  ({ app, db } = createTestApp());
});

describe('GET /pagamentos', () => {
  it('retorna array não-vazio', async () => {
    const res = await request(app).get('/pagamentos');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
  });

  it('cada item tem descricao, valor (number) e formas (array)', async () => {
    const res = await request(app).get('/pagamentos');
    const item = res.body[0];
    expect(item).toHaveProperty('descricao');
    expect(typeof item.valor).toBe('number');
    expect(Array.isArray(item.formas)).toBe(true);
    expect(item.formas.length).toBeGreaterThan(0);
  });

  it('retorna "Consulta Geral" com valor 150 e 4 formas de pagamento', async () => {
    const res = await request(app).get('/pagamentos');
    const consulta = res.body.find(p => p.descricao === 'Consulta Geral');
    expect(consulta).toBeDefined();
    expect(consulta.valor).toBe(150);
    expect(consulta.formas).toContain('PIX');
  });
});
