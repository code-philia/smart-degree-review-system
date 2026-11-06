import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { afterAll, expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const boundary = require('../src/normative/paperLintProcess');
const original = boundary.runPaperLintProcess;
boundary.runPaperLintProcess = async (_command, args) => {
  expect(args[0]).toMatch(/check_paper_document\.py$/);
  const required = ['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'];
  return { stdout: JSON.stringify({ version: 'paper-admission/2.0', status: 'accepted', compiled: true,
    reason_code: 'paper_structure_incomplete', stage: 'partial', reason: '缺少参考文献部分。',
    sha256: crypto.createHash('sha256').update(await fs.readFile(args[1])).digest('hex'),
    structure: { status: 'rejected', profile: 'chinese-thesis', required_sections: required,
      missing_sections: ['参考文献'], incomplete_sections: [],
      observed_sections: Object.fromEntries(required.map(name => [name, name !== '参考文献'])) } }) };
};
const names = ['paperDocumentAdmission', 'archiveScanService', 'reviewPilotPaperLintService'];
names.forEach(name => { delete require.cache[require.resolve(`../src/normative/${name}`)]; });
const { createArchiveScanService } = require('../src/normative/archiveScanService');
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const harness = createTestDatabaseHarness({ label: 'archive-partial' });
afterAll(() => { boundary.runPaperLintProcess = original; names.forEach(name => { delete require.cache[require.resolve(`../src/normative/${name}`)]; }); });

it('persists an all-unavailable reference selection as inconclusive instead of a failed document', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'archive-partial-'));
  try {
    const db = await harness.setup();
    await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('admin', 'archivepartial', 'hash', 'SCHOOL_ADMIN', 'SCHOOL')");
    await fs.writeFile(path.join(root, 'paper.pdf'), '%PDF-test');
    const service = createArchiveScanService({ archiveRoot: root });
    const job = await service.startJob({ userId: 'admin', ruleIds: ['sjtu_rule_24'] });
    await service.waitForIdle();
    expect(await service.getJob(job.id)).toMatchObject({ completed_count: 1, failed_count: 0, inconclusive_count: 1 });
    const docs = await service.listDocuments(job.id, {});
    const result = (await service.getDocument(job.id, docs.items[0].id)).result;
    expect(result.ruleset.name).toBeTruthy();
    expect(result.summary).toMatchObject({ rule_count: 1, unsupported_rule_count: 1, finding_count: 0 });
    expect(result.rule_runs[0]).toMatchObject({ execution_status: 'unsupported', outcome: 'inconclusive' });
    expect(result.rule_runs).toHaveLength(1);
    expect(result.rule_runs[0].message).toContain('缺少参考文献');
  } finally { await harness.cleanup(); await fs.rm(root, { recursive: true, force: true }); }
});
