const request = require('supertest');
const { createTestApp } = require('./setup');

let app, db;

beforeEach(() => {
  ({ app, db } = createTestApp());
});

describe('GET /pacientes/:email', () => {
  it('retorna paciente existente com 200', async () => {
    const res = await request(app).get('/pacientes/joao@email.com');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('id');
    expect(res.body).toHaveProperty('nome', 'João Silva');
    expect(res.body).toHaveProperty('email', 'joao@email.com');
    expect(res.body).toHaveProperty('telefone');
  });

  it('retorna 404 para email inexistente', async () => {
    const res = await request(app).get('/pacientes/naoexiste@email.com');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Paciente não encontrado' });
  });
});
