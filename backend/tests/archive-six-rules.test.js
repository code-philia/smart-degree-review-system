import { beforeEach, afterEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { promisify } = require('util');
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const { createArchiveScanService } = require('../src/normative/archiveScanService');

const harness = createTestDatabaseHarness({ label: 'archive-six-rules' });
const ids = ['sjtu_rule_11', 'sjtu_rule_13', 'sjtu_rule_14', 'sjtu_rule_15', 'sjtu_rule_16',
  'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_29'];
const previousToken = process.env.MINERU_API_TOKEN;
let root;
let db;
beforeEach(async () => {
  delete process.env.MINERU_API_TOKEN;
  db = await harness.setup();
  await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('admin', 'archiveadmin', 'hash', 'SCHOOL_ADMIN', 'SCHOOL')");
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'archive-six-'));
  fs.writeFileSync(path.join(root, 'one.pdf'), '%PDF-1.4');
  fs.writeFileSync(path.join(root, 'two.pdf'), '%PDF-1.4');
});
afterEach(async () => {
  await harness.cleanup();
  fs.rmSync(root, { recursive: true, force: true });
  if (previousToken === undefined) delete process.env.MINERU_API_TOKEN;
  else process.env.MINERU_API_TOKEN = previousToken;
});

describe('archive scans with six additional rules', () => {
  it('offers ten rules in numeric order and reflects MinerU availability', () => {
    const service = createArchiveScanService({ archiveRoot: root });
    expect(service.rules.map((rule) => rule.rule_id)).toEqual(ids);
    expect(service.rules.filter((rule) => rule.available)).toHaveLength(8);
    process.env.MINERU_API_TOKEN = 'test-token';
    expect(service.rules.filter((rule) => rule.available)).toHaveLength(10);
  });

  it('rejects unconfigured cloud rules before creating a job', async () => {
    const service = createArchiveScanService({ archiveRoot: root });
    await expect(service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_13'] }))
      .rejects.toMatchObject({ status: 400 });
    expect(await service.listJobs()).toEqual([]);
  });

  it('runs a new rule alone and persists results for every archived PDF', async () => {
    const service = createArchiveScanService({ archiveRoot: root, detector: async (_file, selected) => ({
      rule_runs: selected.map((rule_id) => ({ rule_id, outcome: 'passed', findings: [] })),
      summary: { finding_count: 0 },
    }) });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_29'] });
    await service.waitForIdle();
    expect((await service.getJob(job.id)).completed_count).toBe(2);
    const documents = await service.listDocuments(job.id, { ruleId: 'sjtu_rule_29', outcome: 'passed' });
    expect(documents.total).toBe(2);
    expect((await service.getDocument(job.id, documents.items[0].id)).result.rule_runs[0].rule_id)
      .toBe('sjtu_rule_29');
  });

  it('dispatches a mixed ten-rule scan to both engines and stores coordinates and inconclusive outcomes', async () => {
    process.env.MINERU_API_TOKEN = 'test-token';
    const filenames = [
      '../src/normative/archiveScanService',
      '../src/normative/localFiveRulePaperLintService',
      '../src/normative/sixRulePaperLintService',
    ].map((name) => require.resolve(name));
    const original = childProcess.execFile;
    const calls = [];
    const box = { x1: 10, y1: 20, x2: 60, y2: 80, width: 595, height: 842 };
    const fake = () => { throw new Error('Expected promisified runner'); };
    fake[promisify.custom] = async (_python, args) => {
      calls.push(args);
      const old = args[0].endsWith('/five_rule_detector.py');
      const rules = old ? {
        18: { status: 'completed', findings: [] }, 22: { status: 'completed', findings: [] },
        24: { status: 'completed', findings: [] }, 28: { status: 'completed', findings: [] },
      } : {
        11: { status: 'completed', findings: [{ message: '图 99 不存在',
          location: { type: 'pdf_bbox', page_number: 2, bounding_rect: box, rects: [box] } }] },
        13: { status: 'unsupported', reason: '解析无法判定', findings: [] },
        14: { status: 'completed', findings: [] }, 15: { status: 'completed', findings: [] },
        16: { status: 'completed', findings: [] }, 29: { status: 'completed', findings: [] },
      };
      return { stdout: JSON.stringify({ rules }) };
    };
    let service;
    try {
      childProcess.execFile = fake;
      filenames.forEach((filename) => { delete require.cache[filename]; });
      service = require('../src/normative/archiveScanService').createArchiveScanService({ archiveRoot: root });
      const job = await service.startJob({ userId: 'admin', ruleIds: [...ids].reverse() });
      await service.waitForIdle();
      const saved = await service.getJob(job.id);
      expect(saved.selected_rule_ids).toEqual(ids);
      expect(saved.completed_count).toBe(2);
      expect(saved.failed_count).toBe(0);
      expect(saved.finding_count).toBe(2);
      expect(saved.inconclusive_count).toBe(2);
      expect(calls).toHaveLength(4);
      for (const args of calls) {
        expect(fs.existsSync(args[2])).toBe(true);
        expect(args.slice(3)).toEqual(args[0].endsWith('/five_rule_detector.py')
          ? ['--rule', '18', '--rule', '22', '--rule', '24', '--rule', '28']
          : ['--rule', '11', '--rule', '13', '--rule', '14', '--rule', '15', '--rule', '16', '--rule', '29']);
      }
      const documents = await service.listDocuments(job.id, { ruleId: 'sjtu_rule_11', outcome: 'issues_found' });
      expect(documents.total).toBe(2);
      const report = (await service.getDocument(job.id, documents.items[0].id)).result;
      expect(report.rule_runs.map((run) => run.rule_id)).toEqual(ids);
      expect(report.summary.finding_count).toBe(1);
      expect(report.rule_runs[0].findings[0].location.bounding_rect).toEqual(box);
      expect(report.rule_runs[1].outcome).toBe('inconclusive');
    } finally {
      if (service) await service.waitForIdle();
      childProcess.execFile = original;
      filenames.forEach((filename) => { delete require.cache[filename]; });
    }
  });
});
