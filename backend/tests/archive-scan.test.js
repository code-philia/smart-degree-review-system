import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const { createArchiveScanService } = require('../src/normative/archiveScanService');

const harness = createTestDatabaseHarness({ label: 'archive-scan' });
let archive;
let db;
const result = (ids) => ({
  type: 'paper_lint',
  rule_runs: ids.map((rule_id) => ({
    rule_id,
    execution_status: 'completed',
    outcome: 'issues_found',
    findings: [
      {
        finding_id: 'f1',
        message: '问题',
        location: { type: 'pdf_bbox', page_number: 2, bounding_rect: { x1: 1, y1: 1, x2: 2, y2: 2 } },
      },
    ],
  })),
  summary: { finding_count: ids.length },
});

beforeEach(async () => {
  db = await harness.setup();
  await db.run(
    "INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('admin', 'archiveadmin', 'hash', 'SCHOOL_ADMIN', 'SCHOOL')",
  );
  archive = fs.mkdtempSync(path.join(os.tmpdir(), 'archive-scan-'));
  fs.mkdirSync(path.join(archive, 'doctoral'));
  fs.writeFileSync(path.join(archive, 'doctoral', 'one.pdf'), '%PDF-1.4');
  fs.writeFileSync(path.join(archive, 'two.pdf'), '%PDF-1.4');
});
afterEach(async () => {
  await harness.cleanup();
  fs.rmSync(archive, { recursive: true, force: true });
});

describe('archive scan jobs', () => {
  it('persists every paper and selected-rule findings without storing PDF bytes', async () => {
    const service = createArchiveScanService({ archiveRoot: archive, detector: async (_path, ids) => result(ids) });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_18', 'sjtu_rule_22'] });
    await service.waitForIdle();
    const saved = await service.getJob(job.id);
    expect(saved.status).toBe('completed');
    expect(saved.total_count).toBe(2);
    expect(saved.completed_count).toBe(2);
    const rows = await service.listDocuments(job.id, { outcome: 'issues_found', ruleId: 'sjtu_rule_22' });
    expect(rows.items).toHaveLength(2);
    expect((await service.getDocument(job.id, rows.items[0].id)).result.rule_runs).toHaveLength(2);
    expect(await db.get('SELECT COUNT(*) AS count FROM archive_scan_documents WHERE result_json IS NOT NULL')).toEqual({
      count: 2,
    });
  });

  it('continues after a paper fails and resumes unfinished papers', async () => {
    let calls = 0;
    const service = createArchiveScanService({
      archiveRoot: archive,
      detector: async (file, ids) => {
        calls++;
        if (file.endsWith('one.pdf')) throw Error('corrupt');
        return result(ids);
      },
    });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_18'] });
    await service.waitForIdle();
    const saved = await service.getJob(job.id);
    expect(saved.failed_count).toBe(1);
    expect(saved.completed_count).toBe(1);
    expect(calls).toBe(2);
    await db.run("UPDATE archive_scan_jobs SET status='running' WHERE id=?", [job.id]);
    await db.run("UPDATE archive_scan_documents SET status='running' WHERE job_id=? AND status='failed'", [job.id]);
    const resumed = createArchiveScanService({ archiveRoot: archive, detector: async (_file, ids) => result(ids) });
    await resumed.resumeJobs();
    await resumed.waitForIdle();
    expect((await resumed.getJob(job.id)).completed_count).toBe(2);
  });

  it('keeps older completed jobs available in history', async () => {
    const service = createArchiveScanService({ archiveRoot: archive, detector: async (_file, ids) => result(ids) });
    for (let index = 0; index < 51; index++) {
      await db.run(
        "INSERT INTO archive_scan_jobs (id, created_by, selected_rule_ids_json, status, total_count) VALUES (?, 'admin', '[\"sjtu_rule_18\"]', 'completed', 0)",
        [`history-${index}`],
      );
    }
    expect((await service.listJobs()).length).toBe(51);
  });

  it('returns a conflict rather than a server error for simultaneous starts', async () => {
    await db.run(
      "INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('admin2', 'archiveadmin2', 'hash', 'COLLEGE_ADMIN', 'COLLEGE')",
    );
    const service = createArchiveScanService({ archiveRoot: archive, detector: async (_file, ids) => result(ids) });
    const attempts = await Promise.allSettled([
      service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_18'] }),
      service.startJob({ userId: 'admin2', ruleIds: ['sjtu_rule_22'] }),
    ]);
    await service.waitForIdle();
    expect(attempts.filter((item) => item.status === 'fulfilled')).toHaveLength(1);
    expect(attempts.filter((item) => item.status === 'rejected')[0].reason.status).toBe(409);
  });

  it('rejects unsupported rule sets and a second active job', async () => {
    let release;
    const blocked = new Promise((resolve) => {
      release = resolve;
    });
    const service = createArchiveScanService({
      archiveRoot: archive,
      detector: async (_file, ids) => {
        await blocked;
        return result(ids);
      },
    });
    await expect(service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_17'] })).rejects.toMatchObject({
      status: 400,
    });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_18'] });
    await expect(service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_22'] })).rejects.toMatchObject({
      status: 409,
    });
    release();
    await service.waitForIdle();
    expect((await service.getJob(job.id)).status).toBe('completed');
  });

  it('counts inconclusive papers separately from passing papers', async () => {
    const service = createArchiveScanService({
      archiveRoot: archive,
      detector: async (_file, ids) => ({
        rule_runs: ids.map((rule_id) => ({ rule_id, outcome: 'inconclusive', findings: [] })),
        summary: { finding_count: 0 },
      }),
    });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_24'] });
    await service.waitForIdle();
    expect((await service.getJob(job.id)).inconclusive_count).toBe(2);
    expect((await service.listDocuments(job.id, { outcome: 'inconclusive' })).total).toBe(2);
  });

  it('scans a PDF above the upload size limit directly from its archive path', async () => {
    const large = path.join(archive, 'large.pdf');
    fs.writeFileSync(large, '%PDF-1.4');
    fs.truncateSync(large, 55 * 1024 * 1024);
    let sawLarge = false;
    const service = createArchiveScanService({
      archiveRoot: archive,
      detector: async (file, ids) => {
        if (file === large) sawLarge = fs.statSync(file).size > 50 * 1024 * 1024;
        return result(ids);
      },
    });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_18'] });
    await service.waitForIdle();
    expect(sawLarge).toBe(true);
    expect((await service.getJob(job.id)).total_count).toBe(3);
  });

  it('does not follow symlinks outside the archive', async () => {
    fs.symlinkSync('/etc/passwd', path.join(archive, 'outside.pdf'));
    const service = createArchiveScanService({ archiveRoot: archive, detector: async (_file, ids) => result(ids) });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_18'] });
    await service.waitForIdle();
    expect((await service.getJob(job.id)).total_count).toBe(2);
  });
});
