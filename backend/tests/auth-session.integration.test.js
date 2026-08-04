const express = require('express');
const request = require('supertest');
const { afterAll, beforeAll, describe, expect, it } = require('vitest');

const app = require('../src/app');
const { requireAuth } = require('../src/auth/authMiddleware');
const { createTestDatabaseHarness, get, run, seedDatabase } = require('../src/database');

const REQ_ID = 'FEAT-AUTH-SESSION';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

function cookieValue(response) {
  return response.headers['set-cookie']?.find((cookie) => cookie.startsWith('arc_session='));
}

describe('FEAT-AUTH-SESSION backend auth session contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-auth-session', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('seeds exactly four demo accounts idempotently with bcrypt hashes and required relationships', async () => {
    await seedDatabase();

    const users = await get(
      `SELECT COUNT(*) AS total,
              SUM(CASE WHEN password_hash = ? THEN 1 ELSE 0 END) AS plaintext_count
         FROM auth_users
        WHERE username IN ('student01', 'supervisor01', 'college_admin01', 'school_admin01')`,
      [demoPassword],
    );
    const student = await get(
      `SELECT username, role, college_id AS collegeId, supervisor_id AS supervisorId, scope, password_hash AS passwordHash
         FROM auth_users
        WHERE username = 'student01'`,
    );

    expect(users.total).toBe(4);
    expect(users.plaintext_count).toBe(0);
    expect(student).toMatchObject({
      username: 'student01',
      role: 'STUDENT',
      collegeId: 'college01',
      supervisorId: 'supervisor01',
      scope: 'COLLEGE',
    });
    expect(student.passwordHash).toMatch(/^\$2[aby]\$/);
  });

  it('logs in student01 with a HttpOnly SameSite=Lax cookie and restores the full session user', async () => {
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

    const currentUserResponse = await request(app)
      .get('/api/auth/me')
      .set('Cookie', sessionCookie)
      .expect(200);

    expect(currentUserResponse.body.user).toEqual(loginResponse.body.user);
  });

  it('rejects anonymous current-user and protected business API requests without returning data', async () => {
    await request(app)
      .get('/api/auth/me')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.user).toBeUndefined();
      });

    const protectedApp = express();
    protectedApp.get('/api/protected-business', requireAuth(), (req, res) => {
      res.json({ records: [{ owner: req.user.username }] });
    });

    await request(protectedApp)
      .get('/api/protected-business')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.records).toBeUndefined();
      });
  });

  it('enforces role and data scope at the server middleware boundary', async () => {
    const protectedApp = express();
    protectedApp.get(
      '/api/college01-only',
      requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'], scope: { collegeId: 'college01' } }),
      (req, res) => res.json({ username: req.user.username, collegeId: req.user.collegeId }),
    );
    protectedApp.get(
      '/api/college02-only',
      requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'], scope: { collegeId: 'college02' } }),
      (req, res) => res.json({ shouldNotLeak: true }),
    );
    protectedApp.get(
      '/api/school-admin-only',
      requireAuth({ allowedRoles: ['SCHOOL_ADMIN'] }),
      (req, res) => res.json({ username: req.user.username }),
    );

    const studentLogin = await request(app)
      .post('/api/auth/login')
      .send({ username: 'student01', password: demoPassword })
      .expect(200);
    const schoolAdminLogin = await request(app)
      .post('/api/auth/login')
      .send({ username: 'school_admin01', password: demoPassword })
      .expect(200);

    await request(protectedApp)
      .get('/api/college01-only')
      .set('Cookie', cookieValue(studentLogin))
      .expect(200)
      .expect(({ body }) => expect(body).toMatchObject({ username: 'student01', collegeId: 'college01' }));

    await request(protectedApp)
      .get('/api/college02-only')
      .set('Cookie', cookieValue(studentLogin))
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.shouldNotLeak).toBeUndefined();
      });

    await request(protectedApp)
      .get('/api/college02-only')
      .set('Cookie', cookieValue(schoolAdminLogin))
      .expect(200);

    await request(protectedApp)
      .get('/api/school-admin-only')
      .set('Cookie', cookieValue(studentLogin))
      .expect(403);
  });

  it('deletes expired sessions and clears sessions on logout', async () => {
    const loginResponse = await request(app)
      .post('/api/auth/login')
      .send({ username: 'student01', password: demoPassword })
      .expect(200);
    const sessionCookie = cookieValue(loginResponse);
    const sessionId = /arc_session=([^;]+)/.exec(sessionCookie)[1];

    await request(app).post('/api/auth/logout').set('Cookie', sessionCookie).expect(204);
    await request(app).get('/api/auth/me').set('Cookie', sessionCookie).expect(401);

    const expiredSessionId = 'expired-session-for-feat-auth-session';
    await run(
      `INSERT INTO auth_sessions (id, user_id, expires_at)
       VALUES (?, ?, ?)`,
      [expiredSessionId, 'student01', new Date(Date.now() - 1000).toISOString()],
    );

    await request(app)
      .get('/api/auth/me')
      .set('Cookie', `arc_session=${expiredSessionId}`)
      .expect(401);

    const expired = await get('SELECT id FROM auth_sessions WHERE id = ?', [expiredSessionId]);
    const loggedOut = await get('SELECT id FROM auth_sessions WHERE id = ?', [sessionId]);
    expect(expired).toBeNull();
    expect(loggedOut).toBeNull();
  });
});
