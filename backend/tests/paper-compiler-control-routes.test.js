import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database');
const authRoutes = require('../src/auth/authRoutes');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
let harness, directory, app;
const cookies = {};
let frozen = false;
const control = { runCompilerControl: async (action, options = {}) => {
  if (action === 'history') return [{ action: 'set_freeze', freeze: frozen }];
  if (action === 'freeze') frozen = true;
  if (action === 'unfreeze') frozen = false;
  return { freeze: frozen, generation: 1, active_version: action === 'rollback' ? options.version : null, active_path: null };
} };
beforeAll(async () => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), 'compiler-control-route-test-'));
  harness = createTestDatabaseHarness({ dbPath: path.join(directory, 'test.sqlite3'), seedDefault: true }); await harness.setup();
  app = express(); app.use('/auth', express.json(), authRoutes);
  app.use('/paper-lint', createReviewPilotPaperLintRouter({}, {}, {}, control));
  for (const username of ['student01', 'supervisor01', 'college_admin01', 'school_admin01']) {
    const login = await request(app).post('/auth/login').send({ username, password: 'ArcDemo123!' }).expect(200);
    cookies[username] = login.headers['set-cookie'].find(value => value.startsWith('arc_session='));
  }
});
afterAll(async () => { await harness.cleanup(); fs.rmSync(directory, { recursive: true, force: true }); });
describe('global compiler controls', () => {
  it('requires authentication and denies ordinary users every control route', async () => {
    await request(app).get('/paper-lint/control').expect(401);
    for (const username of ['student01', 'supervisor01']) {
      await request(app).get('/paper-lint/control').set('Cookie', cookies[username]).expect(403);
      await request(app).put('/paper-lint/control/freeze').set('Cookie', cookies[username]).send({ freeze: true }).expect(403);
      await request(app).get('/paper-lint/control/history').set('Cookie', cookies[username]).expect(403);
      await request(app).post('/paper-lint/control/rollback').set('Cookie', cookies[username]).send({ version_id: 'v1' }).expect(403);
    }
  });
  it('lets both existing administrator roles inspect and persist freeze as a real boolean', async () => {
    for (const username of ['college_admin01', 'school_admin01']) {
      const cookie = cookies[username];
      expect((await request(app).get('/paper-lint/control').set('Cookie', cookie).expect(200)).body.freeze).toBeTypeOf('boolean');
      expect((await request(app).put('/paper-lint/control/freeze').set('Cookie', cookie).send({ freeze: true }).expect(200)).body.freeze).toBe(true);
      expect((await request(app).put('/paper-lint/control/freeze').set('Cookie', cookie).send({ freeze: false }).expect(200)).body.freeze).toBe(false);
    }
  });
  it('rejects coercible freeze values and exposes only explicit history and rollback operations', async () => {
    const cookie = cookies.school_admin01;
    await request(app).put('/paper-lint/control/freeze').set('Cookie', cookie).send({ freeze: 'false' }).expect(400);
    expect((await request(app).get('/paper-lint/control/history').set('Cookie', cookie).expect(200)).body[0].action).toBe('set_freeze');
    expect((await request(app).post('/paper-lint/control/rollback').set('Cookie', cookie).send({ version_id: 'v1' }).expect(200)).body.active_version).toBe('v1');
    await request(app).post('/paper-lint/control/rollback').set('Cookie', cookie).send({}).expect(400);
  });
});
