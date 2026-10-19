#!/usr/bin/env node
const fs = require('fs/promises');
const path = require('path');

const workspace = path.resolve(__dirname, '../../..');
const defaultInput = path.join(workspace, 'data/legacy-scan-export-20261018/documents.jsonl');
const defaultOutput = path.join(workspace, 'outputs/repair-experiment-20261019.json');
const defaultDb = path.join(workspace, 'runtime/repair-experiment-20261019.sqlite');
const wantedRules = ['sjtu_rule_11', 'sjtu_rule_15', 'sjtu_rule_16', 'sjtu_rule_18', 'sjtu_rule_22'];

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? path.resolve(process.argv[index + 1]) : fallback;
}

function firstFindings(documents) {
  return wantedRules.map((ruleId) => {
    for (const document of documents) {
      const ruleRun = document.result?.rule_runs?.find((run) => run.rule_id === ruleId);
      const finding = ruleRun?.findings?.[0];
      if (finding) return { document, ruleRun, finding };
    }
    throw new Error(`归档导出中没有 ${ruleId} 的告警`);
  });
}

async function seedArchive(db, rows) {
  await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('experiment-admin', 'experiment-admin', 'not-a-login', 'SCHOOL_ADMIN', 'SCHOOL')");
  const jobs = new Set();
  for (const { document } of rows) {
    if (!jobs.has(document.job_id)) {
      jobs.add(document.job_id);
      await db.run(
        "INSERT INTO archive_scan_jobs (id, created_by, selected_rule_ids_json, status, total_count) VALUES (?, 'experiment-admin', '[]', 'completed', 1)",
        [document.job_id],
      );
    }
    await db.run(
      `INSERT INTO archive_scan_documents
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
  process.env.ARC_DB_FILE = dbPath;

  const content = await fs.readFile(input, 'utf8');
  const selected = firstFindings(content.trim().split('\n').map(JSON.parse));
  const db = require('../src/database/db_runtime');
  const { buildArchiveRepairRequestWithPdfContext } = require('../src/normative/repairEvidenceService');
  const { saveRepairSuggestion } = require('../src/normative/repairSuggestionService');
  const { PROMPT_VERSION, buildMessages, proposeRepair } = require('../src/normative/repairModelProposalService');
  const { initializeDatabase } = require('../src/database/init_db');

  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.mkdir(path.dirname(dbPath), { recursive: true });
  await initializeDatabase({ reset: true });
  await seedArchive(db, selected);

  const records = [];
  for (const { document, ruleRun, finding } of selected) {
    const source = { jobId: document.job_id, documentId: document.id, ruleId: ruleRun.rule_id, findingId: finding.finding_id };
    try {
      const request = await buildArchiveRepairRequestWithPdfContext(source);
      const response = await proposeRepair(request);
      await saveRepairSuggestion(request, response);
      records.push({ source, relative_path: document.relative_path, request, prompt_messages: buildMessages(request), response });
    } catch (error) {
      records.push({ source, relative_path: document.relative_path, error: { status: error.status || 500, message: error.message } });
    }
  }
  const report = {
    schema_version: 'repair-experiment-v1', generated_at: new Date().toISOString(),
    input: path.relative(workspace, input), database: path.relative(workspace, dbPath),
    requested_rule_ids: wantedRules, model: process.env.MAAS_MODEL || null,
    model_version: process.env.MAAS_MODEL_VERSION || 'unknown', prompt_version: PROMPT_VERSION,
    records,
  };
  await fs.writeFile(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  const succeeded = records.filter((record) => record.response).length;
  process.stdout.write(`Saved ${succeeded}/${records.length} experiment results to ${output}\n`);
}

main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
