const request = require('supertest');
const { createTestApp } = require('./setup');

let app, db;

beforeEach(() => {
  ({ app, db } = createTestApp());
});

function getFirstAvailableHorario(app) {
  return request(app).get('/horarios/disponiveis').then(res => res.body[0]);
}

describe('POST /agendamentos', () => {
  it('cria agendamento com paciente e horário válidos — retorna 201', async () => {
    const horario = await getFirstAvailableHorario(app);
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'pedro@email.com', horario_id: horario.id });

    expect(res.status).toBe(201);
    expect(res.body).toHaveProperty('id');
    expect(res.body).toHaveProperty('status', 'ativo');
    expect(res.body.paciente).toHaveProperty('email', 'pedro@email.com');
    expect(res.body.horario).toHaveProperty('id', horario.id);
  });

  it('retorna 404 para email de paciente inexistente', async () => {
    const horario = await getFirstAvailableHorario(app);
    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'fantasma@email.com', horario_id: horario.id });

    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Paciente não encontrado' });
  });

  it('retorna 409 para horário já ocupado', async () => {
    // horario_id 1 e 2 estão ocupados pelo seed
    const allHorarios = db.prepare('SELECT id FROM horarios WHERE disponivel=0').all();
    const ocupadoId = allHorarios[0].id;

    const res = await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'joao@email.com', horario_id: ocupadoId });

    expect(res.status).toBe(409);
    expect(res.body).toEqual({ error: 'Horário não está mais disponível' });
  });

  it('horário fica indisponível após agendamento', async () => {
    const horario = await getFirstAvailableHorario(app);
    await request(app)
      .post('/agendamentos')
      .send({ paciente_email: 'pedro@email.com', horario_id: horario.id });

    const horarios = await request(app).get('/horarios/disponiveis');
    const ids = horarios.body.map(h => h.id);
    expect(ids).not.toContain(horario.id);
  });
});

describe('GET /agendamentos/:id', () => {
  it('retorna agendamento existente', async () => {
    const agendamento = db.prepare('SELECT id FROM agendamentos LIMIT 1').get();
    const res = await request(app).get(`/agendamentos/${agendamento.id}`);

    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('id', agendamento.id);
    expect(res.body).toHaveProperty('status');
    expect(res.body).toHaveProperty('paciente');
    expect(res.body).toHaveProperty('horario');
    expect(res.body).toHaveProperty('medico');
  });

  it('retorna 404 para id inexistente', async () => {
    const res = await request(app).get('/agendamentos/99999');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Agendamento não encontrado' });
  });
});

describe('GET /agendamentos', () => {
  it('retorna agendamentos do paciente pelo email — retorna 200 com lista', async () => {
    const res = await request(app).get('/agendamentos?email=joao@email.com');

    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
    expect(res.body[0]).toHaveProperty('paciente');
    expect(res.body[0]).toHaveProperty('horario');
    expect(res.body[0]).toHaveProperty('medico');
    expect(res.body[0].paciente).toHaveProperty('email', 'joao@email.com');
  });

  it('filtra por status quando parâmetro status é fornecido', async () => {
    const res = await request(app).get('/agendamentos?email=joao@email.com&status=ativo');

    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    res.body.forEach(a => expect(a.status).toBe('ativo'));
  });

  it('retorna lista vazia para paciente sem agendamentos', async () => {
    const res = await request(app).get('/agendamentos?email=lucas@email.com');

    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it('retorna 400 quando email está ausente', async () => {
    const res = await request(app).get('/agendamentos');

    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error');
  });

  it('retorna 400 para email inválido', async () => {
    const res = await request(app).get('/agendamentos?email=nao-e-email');

    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error');
  });
});

describe('PATCH /agendamentos/:id/cancelar', () => {
  it('cancela agendamento ativo — retorna 200 com status cancelado', async () => {
    const agendamento = db.prepare("SELECT id FROM agendamentos WHERE status='ativo' LIMIT 1").get();
    const res = await request(app).patch(`/agendamentos/${agendamento.id}/cancelar`);

    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('id', agendamento.id);
    expect(res.body).toHaveProperty('status', 'cancelado');
  });

  it('retorna 404 para id inexistente', async () => {
    const res = await request(app).patch('/agendamentos/99999/cancelar');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Agendamento não encontrado' });
  });

  it('retorna 400 para agendamento já cancelado', async () => {
    const agendamento = db.prepare("SELECT id FROM agendamentos WHERE status='ativo' LIMIT 1").get();
    await request(app).patch(`/agendamentos/${agendamento.id}/cancelar`);
    const res = await request(app).patch(`/agendamentos/${agendamento.id}/cancelar`);

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: 'Agendamento já está cancelado' });
  });

  it('horário fica disponível após cancelamento', async () => {
    const agendamento = db.prepare("SELECT id, horario_id FROM agendamentos WHERE status='ativo' LIMIT 1").get();
    await request(app).patch(`/agendamentos/${agendamento.id}/cancelar`);

    const horarios = await request(app).get('/horarios/disponiveis');
    const ids = horarios.body.map(h => h.id);
    expect(ids).toContain(agendamento.horario_id);
  });
});
