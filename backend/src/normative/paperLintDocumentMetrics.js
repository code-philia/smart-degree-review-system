const { execFile } = require('child_process');
const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');

const COUNTING_METHOD = 'cjk_characters_and_words';
// Bump whenever Python extraction or counting semantics change.
const COUNTING_VERSION = '1';
const MAX_CACHE_BYTES = 8192;
const DEFAULT_TIMEOUT_MS = 30000;
const DEFAULT_OUTPUT_BYTES = 8192;
const script = path.resolve(__dirname, '../../scripts/pdf_document_metrics.py');

function unavailable(status = 503) {
  const error = new Error(status === 410 ? '该报告的原始 PDF 已不可用' : '暂时无法读取 PDF 文档统计，请稍后重试');
  error.status = status;
  return error;
}

function normalizeMetrics(value) {
  if (!value || !Number.isSafeInteger(value.page_count) || value.page_count < 1
    || value.counting_method !== COUNTING_METHOD || typeof value.text_available !== 'boolean'
    || (value.text_available ? !Number.isSafeInteger(value.word_count) || value.word_count < 1 : value.word_count !== null)) {
    throw unavailable();
  }
  return {
    page_count: value.page_count,
    word_count: value.word_count,
    text_available: value.text_available,
    counting_method: COUNTING_METHOD,
  };
}

function resolvePython() {
  return process.env.PAPER_LINT_METRICS_PYTHON || process.env.PAPER_MODEL_PYTHON
    || process.env.FIVE_RULE_PYTHON || process.env.SIX_RULE_PYTHON || 'python3';
}

function extractPdfMetrics(pdfPath, { python, scriptPath, timeoutMs, maxOutputBytes }) {
  return new Promise((resolve, reject) => {
    execFile(python || resolvePython(), [scriptPath, pdfPath], {
      timeout: timeoutMs, maxBuffer: maxOutputBytes, killSignal: 'SIGKILL',
      encoding: 'utf8', windowsHide: true,
    }, (error, stdout) => {
      if (error) return reject(unavailable());
      try { return resolve(normalizeMetrics(JSON.parse(stdout))); }
      catch { return reject(unavailable()); }
    });
  });
}

async function pdfStat(pdfPath) {
  try {
    const stat = await fs.promises.stat(pdfPath);
    if (!stat.isFile()) throw unavailable(410);
    return { size: stat.size, mtime_ms: stat.mtimeMs };
  } catch (error) {
    if (error.code === 'ENOENT') throw unavailable(410);
    throw error;
  }
}

function samePdf(first, second) {
  return first?.size === second?.size && first?.mtime_ms === second?.mtime_ms;
}

async function readCache(cachePath, stat) {
  let handle;
  try {
    handle = await fs.promises.open(cachePath, 'r');
    const bytes = Buffer.alloc(MAX_CACHE_BYTES + 1);
    const { bytesRead } = await handle.read(bytes, 0, bytes.length, 0);
    if (bytesRead > MAX_CACHE_BYTES) return null;
    const cached = JSON.parse(bytes.subarray(0, bytesRead).toString('utf8'));
    if (cached.counting_version !== COUNTING_VERSION || !samePdf(cached.pdf, stat)) return null;
    return normalizeMetrics(cached.metrics);
  } catch {
    return null;
  } finally {
    if (handle) await handle.close().catch(() => {});
  }
}

async function writeCache(cachePath, stat, metrics) {
  const temporary = `${cachePath}.${randomUUID()}.tmp`;
  try {
    await fs.promises.writeFile(temporary, JSON.stringify({
      counting_version: COUNTING_VERSION, pdf: stat, metrics,
    }), { flag: 'wx', mode: 0o600 });
    // A deletion or replacement during extraction must not leave a stale cache.
    if (samePdf(stat, await pdfStat(cachePath.slice(0, -'.metrics.json'.length)))) {
      await fs.promises.rename(temporary, cachePath);
    }
  } catch {
    // The cache is optional, including on read-only report directories.
  } finally {
    await fs.promises.rm(temporary, { force: true }).catch(() => {});
  }
}

function createDocumentMetricsService({
  extractMetrics,
  python,
  scriptPath = script,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  maxOutputBytes = DEFAULT_OUTPUT_BYTES,
} = {}) {
  const inFlight = new Map();
  const extract = extractMetrics || (pdfPath => extractPdfMetrics(pdfPath, { python, scriptPath, timeoutMs, maxOutputBytes }));

  async function getPaperLintDocumentMetrics(pdfPath) {
    const absolutePath = path.resolve(pdfPath);
    const pending = inFlight.get(absolutePath);
    if (pending) return pending;
    const operation = (async () => {
      const stat = await pdfStat(absolutePath);
      const cachePath = `${absolutePath}.metrics.json`;
      const cached = await readCache(cachePath, stat);
      if (cached) return cached;
      const metrics = normalizeMetrics(await extract(absolutePath));
      const latestStat = await pdfStat(absolutePath);
      if (samePdf(stat, latestStat)) await writeCache(cachePath, stat, metrics);
      return metrics;
    })();
    inFlight.set(absolutePath, operation);
    try { return await operation; }
    finally { if (inFlight.get(absolutePath) === operation) inFlight.delete(absolutePath); }
  }

  return { getPaperLintDocumentMetrics };
}

module.exports = { ...createDocumentMetricsService(), createDocumentMetricsService };
