import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');

const REQ_ID = 'FEAT-AUTH-PASSWORD';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

function cookieValue(response) {
  return response.headers['set-cookie']?.find((cookie) => cookie.startsWith('arc_session='));
}

describe('FEAT-AUTH-PASSWORD API credential login contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-auth-password', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('accepts student01 credentials and exposes a safe session user for role-aware UI', async () => {
    const loginResponse = await request(app)
      .post('/api/auth/login')
      .send({ username: 'student01', password: demoPassword })
      .expect(200);

    const sessionCookie = cookieValue(loginResponse);
    expect(sessionCookie).toContain('HttpOnly');
    expect(sessionCookie).toMatch(/SameSite=Lax/i);
    expect(loginResponse.body.user).toEqual({
      id: 'student01',
      username: 'student01',
      role: 'STUDENT',
      collegeId: 'college01',
      supervisorId: 'supervisor01',
      scope: 'COLLEGE',
    });
    expect(loginResponse.body.user.passwordHash).toBeUndefined();
    expect(loginResponse.body.user.password).toBeUndefined();

    await request(app)
      .get('/api/auth/me')
      .set('Cookie', sessionCookie)
      .expect(200)
      .expect(({ body }) => expect(body.user).toEqual(loginResponse.body.user));
  });

  it('rejects wrong and missing-user credentials with the same generic response and without setting a session cookie', async () => {
    const wrongPasswordResponse = await request(app)
      .post('/api/auth/login')
      .send({ username: 'student01', password: 'WrongPassword123!' })
      .expect(401);
    const missingUserResponse = await request(app)
      .post('/api/auth/login')
      .send({ username: 'missing-user', password: 'WrongPassword123!' })
      .expect(401);

    expect(wrongPasswordResponse.body).toEqual(missingUserResponse.body);
    expect(wrongPasswordResponse.body).toMatchObject({ code: 401 });
    expect(cookieValue(wrongPasswordResponse)).toBeUndefined();
    expect(cookieValue(missingUserResponse)).toBeUndefined();
    expect(wrongPasswordResponse.body.user).toBeUndefined();
    expect(missingUserResponse.body.user).toBeUndefined();
  });

  it('denies anonymous current-session requests before returning user data', async () => {
    await request(app)
      .get('/api/auth/me')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.user).toBeUndefined();
      });
  });
});
