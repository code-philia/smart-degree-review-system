const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

const filename = path.resolve(__dirname, '../src/normative/archiveScanService.js');

function serviceWithRepository(repository, options) {
  const supplied = {
    '../database/db_runtime': repository,
    './localFiveRulePaperLintService': { LOCAL_RULES: [], isLocalRuleId: () => false },
    './sixRulePaperLintService': { getSixRules: () => [], isSixRuleId: () => true },
    './reviewPilotPaperLintService': {},
  };
  const module = { exports: {} };
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    module, exports: module.exports, process, console,
    require: (name) => supplied[name] || require(name),
  }, { filename });
  return module.exports.createArchiveScanService(options);
}

function memoryRepository() {
  const job = { id: 'external-job', status: 'running', selected_rule_ids_json: '["sjtu_rule_15"]',
    total_count: 2, completed_count: 0, failed_count: 0, inconclusive_count: 0, finding_count: 0 };
  const documents = [
    { id: 'first', relative_path: 'first.pdf', status: 'running' },
    { id: 'second', relative_path: 'second.pdf', status: 'pending' },
  ];
  const repository = {
    job, documents,
    async get(sql) {
      if (sql.includes("WHERE status='running'")) return job.status === 'running' ? { id: job.id } : null;
      if (sql.includes('SELECT * FROM archive_scan_jobs')) return { ...job };
      throw new Error('Unexpected repository read');
    },
    async all(sql) {
      if (!sql.includes('archive_scan_documents')) throw new Error('Unexpected repository list');
      return documents.filter(doc => ['pending', 'running'].includes(doc.status)).map(doc => ({ ...doc }));
    },
    async run(sql, params = []) {
      if (sql.includes("SET status='pending'")) {
        for (const doc of documents) if (doc.status === 'running') doc.status = 'pending';
      } else if (sql.includes("archive_scan_documents SET status='running'")) {
        documents.find(doc => doc.id === params[0]).status = 'running';
      } else if (sql.includes("archive_scan_documents SET status='completed'")) {
        documents.find(doc => doc.id === params[3]).status = 'completed';
      } else if (sql.includes('completed_count=completed_count+1')) {
        job.completed_count += 1; job.finding_count += params[0]; job.inconclusive_count += params[1];
      } else if (sql.includes("archive_scan_jobs SET status='completed'")) {
        job.status = 'completed';
      } else {
        throw new Error('Unexpected repository write');
      }
    },
    async withTransaction(work) { return work(repository); },
  };
  return repository;
}

async function scenario(value, body) {
  const original = process.env.ARCHIVE_SCAN_EXTERNAL_SUPERVISOR;
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'archive-resume-guard-'));
  try {
    if (value === undefined) delete process.env.ARCHIVE_SCAN_EXTERNAL_SUPERVISOR;
    else process.env.ARCHIVE_SCAN_EXTERNAL_SUPERVISOR = value;
    fs.writeFileSync(path.join(directory, 'first.pdf'), '%PDF-synthetic');
    fs.writeFileSync(path.join(directory, 'second.pdf'), '%PDF-synthetic');
    const repository = memoryRepository();
    const scans = [];
    const service = serviceWithRepository(repository, {
      archiveRoot: directory,
      detector: async (pdf, ruleIds) => {
        scans.push({ pdf: path.basename(pdf), ruleIds: [...ruleIds] });
        return { rule_runs: [{ rule_id: 'sjtu_rule_15', outcome: 'passed' }], summary: { finding_count: 0 } };
      },
    });
    await body(service, repository, scans);
  } finally {
    if (original === undefined) delete process.env.ARCHIVE_SCAN_EXTERNAL_SUPERVISOR;
    else process.env.ARCHIVE_SCAN_EXTERNAL_SUPERVISOR = original;
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

test('external supervisor flag preserves running/pending documents without detector dispatch', async () => {
  await scenario('1', async (service, repository, scans) => {
    const before = JSON.stringify({ job: repository.job, documents: repository.documents });
    await service.resumeJobs();
    await service.waitForIdle();
    assert.equal(JSON.stringify({ job: repository.job, documents: repository.documents }), before);
    assert.deepEqual(scans, []);
  });
});

test('without the external supervisor flag ordinary running job still resumes every document', async () => {
  await scenario(undefined, async (service, repository, scans) => {
    await service.resumeJobs();
    await service.waitForIdle();
    assert.deepEqual(scans.map(scan => scan.pdf), ['first.pdf', 'second.pdf']);
    assert.deepEqual(scans.map(scan => scan.ruleIds), [['sjtu_rule_15'], ['sjtu_rule_15']]);
    assert.deepEqual(repository.documents.map(doc => doc.status), ['completed', 'completed']);
    assert.equal(repository.job.status, 'completed');
    assert.equal(repository.job.completed_count, 2);
  });
});
