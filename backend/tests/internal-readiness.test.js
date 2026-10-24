import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'paper-repair-readiness-'));
process.env.ARC_READINESS_TOKEN = 'test-readiness-token';
process.env.PAPER_LINT_REPORTS_DIR = path.join(root, 'reports');
process.env.PAPER_LINT_JOBS_DIR = path.join(root, 'jobs');
process.env.PAPER_COMPILER_CACHE_ROOT = path.join(root, 'cache');
process.env.PAPER_COMPILER_CONFIG = path.join(root, 'private.env');
process.env.PAPER_COMPILER_LEDGER = path.join(root, 'ledger.sqlite3');
process.env.MAAS_API_KEY = 'test-only-sentinel';
process.env.MAAS_BASE_URL = 'https://example.invalid';
process.env.MAAS_MODEL = 'test-model';
fs.mkdirSync(process.env.PAPER_LINT_REPORTS_DIR, { recursive: true });
fs.mkdirSync(process.env.PAPER_LINT_JOBS_DIR, { recursive: true });
fs.mkdirSync(process.env.PAPER_COMPILER_CACHE_ROOT, { recursive: true });
fs.writeFileSync(process.env.PAPER_COMPILER_CONFIG, 'test-only configuration\n');

const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');

let harness;

describe('internal readiness and storage diagnostics', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'internal-readiness' });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
    fs.rmSync(root, { recursive: true, force: true });
  });

  it('keeps diagnostics private when the token is absent or incorrect', async () => {
    await request(app).get('/api/internal/readiness').expect(404);
    await request(app).get('/api/internal/readiness').set('x-readiness-token', 'wrong').expect(404);
  });

  it('returns health booleans without paths, credentials, or model calls', async () => {
    const response = await request(app)
      .get('/api/internal/readiness')
      .set('x-readiness-token', process.env.ARC_READINESS_TOKEN)
      .expect((result) => expect([200, 503]).toContain(result.status));
    expect(response.body.checks).toBeDefined();
    expect(JSON.stringify(response.body)).not.toContain(process.env.MAAS_API_KEY);
    expect(JSON.stringify(response.body)).not.toContain(process.env.PAPER_COMPILER_CONFIG);
    expect(response.body.checks.storage_consistency).toMatchObject({
      reports: { count: 0, missing_pdf_count: 0 },
      jobs: { count: 0, missing_pdf_count: 0 },
    });
  });
});
