const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const MAX_PDF_BYTES = 50 * 1024 * 1024;
const MAX_ENGINE_OUTPUT_BYTES = 30 * 1024 * 1024;
const ENGINE_TIMEOUT_MS = 5 * 60 * 1000;
const MAX_CONCURRENT_RUNS = Math.max(1, Number(process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS) || 2);
const bridgeScript = path.resolve(__dirname, '../../scripts/run_review_pilot_deterministic_lint.py');

let catalogPromise = null;
let activeRunCount = 0;
const runQueue = [];

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function resolveEngineBackendDir() {
  if (process.env.REVIEW_PILOT_BACKEND_DIR) {
    return path.resolve(process.env.REVIEW_PILOT_BACKEND_DIR);
  }
  return path.resolve(__dirname, '../../../../projects/review-pilot/backend');
}

function resolveEnginePython(backendDir) {
  if (process.env.REVIEW_PILOT_PYTHON) {
    return path.resolve(process.env.REVIEW_PILOT_PYTHON);
  }
  const venvPython = path.join(backendDir, '.venv', 'bin', 'python');
  return fs.existsSync(venvPython) ? venvPython : 'python3';
}

function assertEngineAvailable(backendDir) {
  if (!fs.existsSync(path.join(backendDir, 'novref', 'domain', 'paper_lint'))) {
    throw createHttpError(503, 'review-pilot 规则引擎尚未安装或路径未配置');
  }
}

function childEnvironment() {
  const env = { ...process.env };
  for (const key of [
    'ALL_PROXY',
    'all_proxy',
    'HTTP_PROXY',
    'http_proxy',
    'HTTPS_PROXY',
    'https_proxy',
  ]) {
    if (typeof env[key] === 'string' && /^socks/i.test(env[key])) {
      delete env[key];
    }
  }
  return env;
}

function parseLastEngineError(stderr) {
  const lines = stderr.trim().split('\n').filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      const parsed = JSON.parse(lines[index]);
      if (typeof parsed.error === 'string' && parsed.error.trim()) return parsed.error;
    } catch {
      // Continue past structured logs emitted by the imported engine.
    }
  }
  return null;
}

function parseLastEnginePayload(stdout) {
  const lines = stdout.trim().split('\n').filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      return JSON.parse(lines[index]);
    } catch {
      // Continue past structured initialization logs emitted by review-pilot.
    }
  }
  throw new Error('missing engine payload');
}

function runBridge(args, timeoutMs = ENGINE_TIMEOUT_MS) {
  const backendDir = resolveEngineBackendDir();
  assertEngineAvailable(backendDir);

  return new Promise((resolve, reject) => {
    const child = spawn(
      resolveEnginePython(backendDir),
      [bridgeScript, '--backend-dir', backendDir, ...args],
      { cwd: backendDir, env: childEnvironment(), shell: false, stdio: ['ignore', 'pipe', 'pipe'] },
    );
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    let outputTooLarge = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    }, timeoutMs);

    child.stdout.on('data', (chunk) => {
      if (outputTooLarge) return;
      stdout += chunk.toString('utf8');
      if (Buffer.byteLength(stdout, 'utf8') > MAX_ENGINE_OUTPUT_BYTES) {
        outputTooLarge = true;
        child.kill('SIGTERM');
      }
    });
    child.stderr.on('data', (chunk) => {
      if (Buffer.byteLength(stderr, 'utf8') < 128 * 1024) stderr += chunk.toString('utf8');
    });
    child.once('error', () => {
      clearTimeout(timer);
      reject(createHttpError(503, 'review-pilot 规则引擎无法启动'));
    });
    child.once('close', (code) => {
      clearTimeout(timer);
      if (timedOut) return reject(createHttpError(504, '规则审查运行超时，请减少规则后重试'));
      if (outputTooLarge) return reject(createHttpError(502, '规则审查结果过大，无法返回'));
      if (code !== 0) {
        return reject(createHttpError(502, parseLastEngineError(stderr) || 'review-pilot 规则审查运行失败'));
      }
      try {
        resolve(parseLastEnginePayload(stdout));
      } catch {
        reject(createHttpError(502, '规则引擎返回了无法解析的结果'));
      }
    });
  });
}

function withRunSlot(callback) {
  return new Promise((resolve, reject) => {
    const start = async () => {
      activeRunCount += 1;
      try {
        resolve(await callback());
      } catch (error) {
        reject(error);
      } finally {
        activeRunCount -= 1;
        runQueue.shift()?.();
      }
    };
    if (activeRunCount < MAX_CONCURRENT_RUNS) start();
    else runQueue.push(start);
  });
}

async function getPaperLintCatalog({ refresh = false } = {}) {
  if (refresh || !catalogPromise) {
    catalogPromise = runBridge(['--catalog'], 60 * 1000).catch((error) => {
      catalogPromise = null;
      throw error;
    });
  }
  return catalogPromise;
}

function validatePdf(pdfBuffer) {
  if (!Buffer.isBuffer(pdfBuffer) || pdfBuffer.length === 0) {
    throw createHttpError(400, '请选择要审查的 PDF 文件');
  }
  if (pdfBuffer.length > MAX_PDF_BYTES) throw createHttpError(413, 'PDF 文件大小不能超过 50 MB');
  if (pdfBuffer.subarray(0, 5).toString('ascii') !== '%PDF-') {
    throw createHttpError(400, '上传内容不是有效的 PDF 文件');
  }
}

function validateSelectedRuleIds(catalog, selectedRuleIds) {
  const knownIds = new Set(catalog.rules.map((rule) => rule.rule_id));
  const normalized = Array.from(
    new Set((selectedRuleIds || []).map((ruleId) => String(ruleId).trim()).filter(Boolean)),
  );
  if (normalized.length === 0) throw createHttpError(400, '请至少选择一条审查规则');
  const unknown = normalized.find((ruleId) => !knownIds.has(ruleId));
  if (unknown) throw createHttpError(400, `未知的审查规则：${unknown}`);
  const unavailable = catalog.rules.find(
    (rule) => normalized.includes(rule.rule_id) && rule.available === false,
  );
  if (unavailable) {
    throw createHttpError(503, `${unavailable.title || unavailable.rule_id}暂不可用，请联系管理员配置语义模型`);
  }
  return normalized;
}

function validateExternalProcessingConsent(catalog, selectedRuleIds, externalProcessingConsent) {
  const externalRule = catalog.rules.find(
    (rule) => selectedRuleIds.includes(rule.rule_id) && rule.uses_external_model === true,
  );
  if (externalRule && !externalProcessingConsent) {
    throw createHttpError(400, '运行 DeepSeek 语义规则前，请先确认论文相关文本允许发送至外部 API');
  }
}

async function normalizeSelectedRuleIds(selectedRuleIds, externalProcessingConsent) {
  const catalog = await getPaperLintCatalog();
  const normalized = validateSelectedRuleIds(catalog, selectedRuleIds);
  validateExternalProcessingConsent(catalog, normalized, externalProcessingConsent);
  return normalized;
}

async function runPaperLint({ pdfBuffer, selectedRuleIds, externalProcessingConsent = false }) {
  validatePdf(pdfBuffer);
  const normalizedRuleIds = await normalizeSelectedRuleIds(selectedRuleIds, externalProcessingConsent);

  return withRunSlot(async () => {
    const tempDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'smart-degree-paper-lint-'));
    const pdfPath = path.join(tempDir, 'input.pdf');
    try {
      await fs.promises.writeFile(pdfPath, pdfBuffer, { flag: 'wx', mode: 0o600 });
      const result = await runBridge([
        '--pdf', pdfPath,
        ...normalizedRuleIds.flatMap((ruleId) => ['--rule', ruleId]),
      ]);
      return { result, selectedRuleIds: normalizedRuleIds };
    } finally {
      await fs.promises.rm(tempDir, { recursive: true, force: true });
    }
  });
}

module.exports = {
  MAX_PDF_BYTES,
  getPaperLintCatalog,
  runPaperLint,
  resolveEngineBackendDir,
  validateExternalProcessingConsent,
  validateSelectedRuleIds,
  validatePdf,
};
