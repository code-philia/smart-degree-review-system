const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');
const { promisify } = require('util');
const { all, get } = require('../database');

const execFileAsync = promisify(execFile);

function configuredPath(value, fallback) {
  return path.resolve(value || fallback);
}

async function checkDirectory(directory) {
  try {
    const stat = await fs.promises.stat(directory);
    return { exists: stat.isDirectory(), readable: true, writable: true };
  } catch (error) {
    if (error.code !== 'ENOENT') return { exists: false, readable: false, writable: false };
    try {
      await fs.promises.access(path.dirname(directory), fs.constants.R_OK | fs.constants.W_OK);
      return { exists: false, readable: true, writable: true };
    } catch {
      return { exists: false, readable: false, writable: false };
    }
  }
}

async function checkPython(python) {
  try {
    await execFileAsync(python, ['-c', 'import pymupdf'], {
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    });
    return true;
  } catch {
    return false;
  }
}

async function checkStorageConsistency() {
  const reports = await all('SELECT id, source_pdf_path FROM paper_lint_reports;');
  const jobs = await all('SELECT id, source_pdf_path, status FROM paper_lint_jobs;');
  const missing = async (rows) => {
    let count = 0;
    for (const row of rows) {
      try {
        const stat = await fs.promises.stat(row.source_pdf_path);
        if (!stat.isFile()) count += 1;
      } catch {
        count += 1;
      }
    }
    return count;
  };
  return {
    reports: { count: reports.length, missing_pdf_count: await missing(reports) },
    jobs: { count: jobs.length, missing_pdf_count: await missing(jobs) },
  };
}

async function buildReadinessSnapshot() {
  const python = process.env.FIVE_RULE_PYTHON || process.env.REVIEW_PILOT_PYTHON ||
    (process.platform === 'win32' ? 'python' : 'python3');
  const reportsDirectory = configuredPath(
    process.env.PAPER_LINT_REPORTS_DIR,
    path.join(process.cwd(), 'data', 'paper-lint-reports'),
  );
  const jobsDirectory = configuredPath(
    process.env.PAPER_LINT_JOBS_DIR,
    path.join(process.cwd(), 'data', 'paper-lint-jobs'),
  );
  const cacheRoot = configuredPath(
    process.env.PAPER_COMPILER_CACHE_ROOT,
    path.join(os.tmpdir(), 'paper-repair-cache'),
  );
  const ledgerPath = process.env.PAPER_COMPILER_LEDGER || '/data/runtime/paper-compiler/budget.sqlite3';
  const [database, reports, jobs, cache] = await Promise.all([
    get('SELECT 1 AS ok;').then(() => true, () => false),
    checkDirectory(reportsDirectory),
    checkDirectory(jobsDirectory),
    checkDirectory(cacheRoot),
  ]);
  const ledger = await checkDirectory(path.dirname(path.resolve(ledgerPath)));
  const pythonAvailable = await checkPython(python);
  const aiConfigured = Boolean(process.env.MAAS_API_KEY && process.env.MAAS_BASE_URL && process.env.MAAS_MODEL);
  const configPath = process.env.PAPER_COMPILER_CONFIG;
  const configReadable = configPath ? await fs.promises.access(configPath, fs.constants.R_OK).then(() => true, () => false) : false;
  const storage = database ? await checkStorageConsistency() : null;
  return {
    ok: database && reports.readable && jobs.readable && pythonAvailable && aiConfigured && configReadable && ledger.readable && cache.readable,
    checks: {
      database,
      pdf_storage: { reports, jobs },
      python: { configured: Boolean(process.env.FIVE_RULE_PYTHON || process.env.REVIEW_PILOT_PYTHON), pymupdf: pythonAvailable },
      ai: { model_configured: aiConfigured, compiler_config_readable: configReadable, ledger_directory_accessible: ledger.readable, cache_directory_accessible: cache.readable },
      storage_consistency: storage,
    },
  };
}

module.exports = { buildReadinessSnapshot, checkStorageConsistency };
