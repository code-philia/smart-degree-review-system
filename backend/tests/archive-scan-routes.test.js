import express from 'express';
import request from 'supertest';
import { beforeAll, afterAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const fs = require('fs');
const os = require('os');
const path = require('path');
const authRoutes = require('../src/auth/authRoutes');
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const { createArchiveScanService } = require('../src/normative/archiveScanService');
const { createArchiveScanRouter } = require('../src/normative/archiveScanRoutes');
const harness = createTestDatabaseHarness({ label: 'archive-scan-routes', seedDefault: true });
let root;
let service;
let app;
const cookies = {};
beforeAll(async () => {
  await harness.setup();
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'archive-routes-'));
  fs.writeFileSync(path.join(root, 'paper.pdf'), '%PDF-1.4\narchive test');
  service = createArchiveScanService({
    archiveRoot: root,
    detector: async (_file, ids) => ({
      rule_runs: ids.map((rule_id) => ({ rule_id, outcome: 'passed', findings: [] })),
      summary: { finding_count: 0 },
    }),
  });
  app = express();
  app.use('/api/auth', express.json(), authRoutes);
  app.use('/api/normative/archive-scans', createArchiveScanRouter(service));
  for (const username of ['student01', 'college_admin01', 'school_admin01']) {
    const login = await request(app).post('/api/auth/login').send({ username, password: 'ArcDemo123!' }).expect(200);
    cookies[username] = login.headers['set-cookie'].find((value) => value.startsWith('arc_session='));
  }
});
afterAll(async () => {
  await service.waitForIdle();
  await harness.cleanup();
  fs.rmSync(root, { recursive: true, force: true });
});
describe('archive scan API', () => {
  it('allows both admins and rejects students', async () => {
    await request(app).get('/api/normative/archive-scans').expect(401);
    await request(app).get('/api/normative/archive-scans').set('Cookie', cookies.student01).expect(403);
    await request(app).get('/api/normative/archive-scans').set('Cookie', cookies.college_admin01).expect(200);
  });
  it('starts a job and serves stored result and original PDF with Range', async () => {
    const response = await request(app)
      .post('/api/normative/archive-scans/jobs')
      .set('Cookie', cookies.school_admin01)
      .send({ selected_rule_ids: ['sjtu_rule_18'] })
      .expect(201);
    await service.waitForIdle();
    const jobId = response.body.job.id;
    const listing = await request(app)
      .get(`/api/normative/archive-scans/jobs/${jobId}/documents`)
      .set('Cookie', cookies.college_admin01)
      .expect(200);
    expect(listing.body.items).toHaveLength(1);
    const id = listing.body.items[0].id;
    const detail = await request(app)
      .get(`/api/normative/archive-scans/jobs/${jobId}/documents/${id}`)
      .set('Cookie', cookies.college_admin01)
      .expect(200);
    expect(detail.body.document.result.rule_runs[0].rule_id).toBe('sjtu_rule_18');
    const pdf = await request(app)
      .get(`/api/normative/archive-scans/jobs/${jobId}/documents/${id}/pdf`)
      .set('Cookie', cookies.college_admin01)
      .set('Range', 'bytes=0-3')
      .expect(206);
    expect(pdf.headers['content-range']).toMatch(/^bytes 0-3\//);
    const tail = await request(app)
      .get(`/api/normative/archive-scans/jobs/${jobId}/documents/${id}/pdf`)
      .set('Cookie', cookies.college_admin01)
      .set('Range', 'bytes=-4')
      .expect(206);
    expect(tail.headers['content-length']).toBe('4');
    expect(tail.headers['content-range']).toMatch(/^bytes \d+-\d+\/\d+$/);
  });
});
