/**
 * B9 (T041): Observability contract — correlation ID propagation.
 * Failing-first: unit tests for requestId.js fail until T043 is implemented.
 */
const request = require('supertest');
const { createTestApp, closeTestPool } = require('./setup');

// ── Unit: requestId middleware (T043) ─────────────────────────────────────────

describe('requestId middleware', () => {
  let requestId;

  beforeAll(() => {
    requestId = require('../src/middlewares/requestId');
  });

  it('is a middleware function', () => {
    expect(typeof requestId).toBe('function');
  });

  it('uses inbound X-Request-ID and sets req.requestId', () => {
    const req = { headers: { 'x-request-id': 'inbound-abc' } };
    const res = { setHeader: jest.fn() };
    const next = jest.fn();
    requestId(req, res, next);
    expect(req.requestId).toBe('inbound-abc');
    expect(res.setHeader).toHaveBeenCalledWith('X-Request-ID', 'inbound-abc');
    expect(next).toHaveBeenCalled();
  });

  it('generates UUID when X-Request-ID is absent', () => {
    const req = { headers: {} };
    const res = { setHeader: jest.fn() };
    const next = jest.fn();
    requestId(req, res, next);
    expect(req.requestId).toMatch(/^[0-9a-f-]{36}$/i);
    expect(res.setHeader).toHaveBeenCalledWith('X-Request-ID', req.requestId);
    expect(next).toHaveBeenCalled();
  });

  it('two requests without X-Request-ID get different IDs', () => {
    const make = () => {
      const req = { headers: {} };
      const res = { setHeader: jest.fn() };
      requestId(req, res, jest.fn());
      return req.requestId;
    };
    expect(make()).not.toBe(make());
  });
});

// ── Integration: header propagation end-to-end ───────────────────────────────

describe('X-Request-ID propagation (B9)', () => {
  let app;

  beforeEach(async () => {
    ({ app } = await createTestApp());
  });

  afterAll(async () => {
    await closeTestPool();
  });

  it('echoes inbound X-Request-ID in response header', async () => {
    const res = await request(app)
      .get('/horarios')
      .set('X-Request-ID', 'echo-id-abc');
    expect(res.headers['x-request-id']).toBe('echo-id-abc');
  });

  it('generates X-Request-ID when none provided', async () => {
    const res = await request(app).get('/horarios');
    expect(res.headers['x-request-id']).toBeDefined();
    expect(res.headers['x-request-id'].length).toBeGreaterThan(8);
  });

  it('error response also carries X-Request-ID', async () => {
    const res = await request(app)
      .post('/agendamentos')
      .set('X-Request-ID', 'error-id-xyz')
      .send({});
    expect(res.headers['x-request-id']).toBe('error-id-xyz');
    expect(res.status).toBeGreaterThanOrEqual(400);
  });
});
