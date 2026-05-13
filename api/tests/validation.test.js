const request = require('supertest');
const { createTestApp } = require('./setup');

let app;

beforeEach(() => {
  ({ app } = createTestApp());
});

describe('Validação de inputs — POST /agendamentos', () => {
  it('retorna 400 para e-mail inválido', async () => {
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: '@@@', horario_id: 1 });
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'E-mail inválido');
  });

  it('retorna 400 para e-mail ausente', async () => {
    const res = await request(app)
      .post('/agendamentos')
      .send({ horario_id: 1 });
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'E-mail inválido');
  });

  it('retorna 400 para horario_id string não-numérico', async () => {
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'joao@email.com', horario_id: 'abc' });
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'horario_id deve ser um número inteiro positivo');
  });

  it('retorna 400 para horario_id zero', async () => {
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'joao@email.com', horario_id: 0 });
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'horario_id deve ser um número inteiro positivo');
  });

  it('retorna 400 para horario_id ausente', async () => {
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'joao@email.com' });
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'horario_id deve ser um número inteiro positivo');
  });
});

describe('Validação de inputs — GET /horarios/disponiveis', () => {
  it('retorna 400 para data malformada', async () => {
    const res = await request(app).get('/horarios/disponiveis?data=2026-13-45');
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'Data inválida. Use formato YYYY-MM-DD');
  });

  it('retorna 400 para data com formato incorreto', async () => {
    const res = await request(app).get('/horarios/disponiveis?data=13/05/2026');
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'Data inválida. Use formato YYYY-MM-DD');
  });

  it('retorna 200 quando data está ausente (lista todos)', async () => {
    const res = await request(app).get('/horarios/disponiveis');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
  });
});

describe('Validação de inputs — GET /pacientes/:email', () => {
  it('retorna 400 para e-mail inválido na rota de pacientes', async () => {
    const res = await request(app).get('/pacientes/invalido@@@');
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'E-mail inválido');
  });
});

describe('Validação de inputs — GET /agendamentos/:id', () => {
  it('retorna 400 para id não-numérico', async () => {
    const res = await request(app).get('/agendamentos/abc');
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'ID inválido');
  });
});

describe('Validação de inputs — PATCH /agendamentos/:id/cancelar', () => {
  it('retorna 400 para id não-numérico', async () => {
    const res = await request(app).patch('/agendamentos/abc/cancelar');
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error', 'ID inválido');
  });
});
