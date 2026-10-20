#!/usr/bin/env node
const fs = require('fs/promises');
const path = require('path');

const workspace = path.resolve(__dirname, '../../..');
const defaultInput = path.join(workspace, 'data/legacy-scan-export-20261018/documents.jsonl');
const defaultOutput = path.join(workspace, 'outputs/repair-batch-20261019-actions-v2.json');
const defaultDb = path.join(workspace, 'runtime/repair-batch-20261019-actions-v2.sqlite');

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? path.resolve(process.argv[index + 1]) : fallback;
}

function numberOption(name) {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = Number(process.argv[index + 1]);
  if (!Number.isSafeInteger(value) || value < 1) throw new Error(`${name} 必须是正整数`);
  return value;
}

function boundedNumberOption(name, fallback, maximum) {
  const value = numberOption(name);
  if (value === null) return fallback;
  if (value > maximum) throw new Error(`${name} 不得超过 ${maximum}`);
  return value;
}

function sourceKey({ jobId, documentId, ruleId, findingId }) {
  return `${jobId}:${documentId}:${ruleId}:${findingId}`;
}

function selectFindings(documents) {
  const selected = [];
  for (const document of documents) {
    for (const ruleRun of document.result?.rule_runs || []) {
      for (const finding of ruleRun.findings || []) {
        selected.push({
          document,
          ruleRun,
          finding,
          source: {
            jobId: document.job_id,
            documentId: document.id,
            ruleId: ruleRun.rule_id,
            findingId: finding.finding_id,
          },
        });
      }
    }
  }
  return selected;
}

async function writeJsonAtomically(filePath, value) {
  const tempPath = `${filePath}.tmp`;
  await fs.writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await fs.rename(tempPath, filePath);
}

async function readExisting(filePath) {
  try { return JSON.parse(await fs.readFile(filePath, 'utf8')); } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

async function seedArchive(db, documents) {
  await db.run("INSERT OR IGNORE INTO auth_users (id, username, password_hash, role, scope) VALUES ('repair-batch-admin', 'repair-batch-admin', 'not-a-login', 'SCHOOL_ADMIN', 'SCHOOL')");
  const jobs = new Set();
  for (const document of documents) {
    if (!jobs.has(document.job_id)) {
      jobs.add(document.job_id);
      await db.run(
        "INSERT OR IGNORE INTO archive_scan_jobs (id, created_by, selected_rule_ids_json, status, total_count) VALUES (?, 'repair-batch-admin', '[]', 'completed', 1)",
        [document.job_id],
      );
    }
    await db.run(
      `INSERT OR IGNORE INTO archive_scan_documents
        (id, job_id, relative_path, filename, size_bytes, status, finding_count, rule_outcomes_json, result_json, finished_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [document.id, document.job_id, document.relative_path, document.filename, document.size_bytes,
        document.status, document.finding_count, JSON.stringify(document.rule_outcomes),
        JSON.stringify(document.result), document.finished_at],
    );
  }
}

async function main() {
  const input = option('--input', defaultInput);
  const output = option('--output', defaultOutput);
  const dbPath = option('--db', defaultDb);
  const limit = numberOption('--limit');
  const concurrency = boundedNumberOption('--concurrency', 1, 5);
  const dryRun = process.argv.includes('--dry-run');
  process.env.ARC_DB_FILE = dbPath;

  const documents = (await fs.readFile(input, 'utf8')).trim().split('\n').map(JSON.parse);
  const allSelected = selectFindings(documents);
  const selected = limit ? allSelected.slice(0, limit) : allSelected;
  if (dryRun) {
    process.stdout.write(`${JSON.stringify({ documents: documents.length, findings: allSelected.length, selected: selected.length }, null, 2)}\n`);
    return;
  }

  const db = require('../src/database/db_runtime');
  const { initializeDatabase } = require('../src/database/init_db');
  const { buildArchiveRepairRequestWithPdfContext } = require('../src/normative/repairEvidenceService');
  const { findRepairSuggestion, saveRepairSuggestion } = require('../src/normative/repairSuggestionService');
  const { PROMPT_VERSION, buildMessages, proposeRepair } = require('../src/normative/repairModelProposalService');

  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.mkdir(path.dirname(dbPath), { recursive: true });
  await initializeDatabase();
  await seedArchive(db, documents);

  const existing = await readExisting(output);
  // Keep every prior record in the report for auditability.  Only successful
  // records are skipped on resume; failed ones remain visible and are retried.
  const recordsByKey = new Map((existing?.records || [])
    .map((record) => [sourceKey(record.source), record]));
  const completed = new Map([...recordsByKey]
    .filter(([, record]) => record.response));
  const report = {
    schema_version: 'repair-batch-v1', started_at: existing?.started_at || new Date().toISOString(),
    updated_at: new Date().toISOString(), input: path.relative(workspace, input), database: path.relative(workspace, dbPath),
    model: process.env.MAAS_MODEL || null, model_version: process.env.MAAS_MODEL_VERSION || 'unknown',
    prompt_version: PROMPT_VERSION, total_findings: allSelected.length, selected_findings: selected.length,
    concurrency,
    records: selected.map(({ source }) => recordsByKey.get(sourceKey(source))).filter(Boolean),
  };

  // Model calls may run concurrently, but shared SQLite writes and the
  // checkpoint file stay serialized so a restart always sees a valid state.
  let checkpointWrite = Promise.resolve();
  async function checkpoint(item, key, record) {
    checkpointWrite = checkpointWrite.then(async () => {
      recordsByKey.set(key, record);
      report.records = selected.map(({ source }) => recordsByKey.get(sourceKey(source))).filter(Boolean);
      report.updated_at = new Date().toISOString();
      await writeJsonAtomically(output, report);
      const successes = report.records.filter((entry) => entry.response).length;
      process.stdout.write(`[${successes}/${selected.length}] ${item.source.ruleId} ${item.source.findingId}${record.error ? ` failed: ${record.error.message}` : ''}\n`);
    });
    return checkpointWrite;
  }

  async function processItem(item) {
    const key = sourceKey(item.source);
    let record;
    try {
      const request = await buildArchiveRepairRequestWithPdfContext(item.source);
      const cached = process.env.MAAS_MODEL ? await findRepairSuggestion(request, {
        model: process.env.MAAS_MODEL,
        modelVersion: process.env.MAAS_MODEL_VERSION || 'unknown',
        promptVersion: PROMPT_VERSION,
      }) : null;
      const response = cached || await proposeRepair(request);
      if (!cached) await saveRepairSuggestion(request, response);
      record = {
        source: item.source, relative_path: item.document.relative_path, request,
        prompt_messages: buildMessages(request), response, cached: Boolean(cached),
      };
      completed.set(key, record);
    } catch (error) {
      record = {
        source: item.source, relative_path: item.document.relative_path,
        error: { status: error.status || 500, message: error.message },
      };
    }
    await checkpoint(item, key, record);
  }

  let nextIndex = 0;
  async function worker() {
    while (nextIndex < selected.length) {
      const item = selected[nextIndex++];
      if (!completed.has(sourceKey(item.source))) await processItem(item);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, selected.length) }, worker));
  await checkpointWrite;
  report.updated_at = new Date().toISOString();
  await writeJsonAtomically(output, report);
}

main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
