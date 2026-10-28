const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { LOCAL_RULES, getLocalRuleAvailability, isLocalRuleId, runLocalFiveRules, summarizeRuleRuns } = require('./localFiveRulePaperLintService');

const { getSixRules, isSixRuleId, runSixRules, SIX_RULE_TIMEOUT_MS } = require('./sixRulePaperLintService');

const { getCompilerRules, isCompilerRuleId, runCompilerRules } = require('./paperCompilerService');
const { runPaperLintRuleGroups } = require('./paperLintRuleRunner');
const { listRuleDefinitions } = require('../../rules/registry');

const RETIRED_RULE_IDS = new Set([
  'claim_evidence_inconsistency_check',
  'strong_claim_without_evidence_check',
]);
const MAX_PDF_BYTES = 50 * 1024 * 1024;
const MAX_ENGINE_OUTPUT_BYTES = 30 * 1024 * 1024;
const ENGINE_TIMEOUT_MS = 5 * 60 * 1000;
const RUN_TIMEOUT_MESSAGE = '规则审查运行超时，请减少规则后重试';
const MAX_CONCURRENT_RUNS = Math.max(1, Number(process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS) || 2);
const bridgeScript = path.resolve(__dirname, '../../scripts/run_review_pilot_deterministic_lint.py');
const bilingualScript = path.resolve(__dirname, '../../scripts/run_bilingual_semantic_lint.py');
const BILINGUAL_RULE_IDS = new Set(['bilingual_abstract_consistency_check', 'bilingual_keywords_correspondence_check', 'typo_detection_check']);

let catalogPromise = null;
let catalogExpiresAt = 0;
let activeRunCount = 0;
const runQueue = [];

function enabledLegacyCatalogRules() {
  return listRuleDefinitions({ family: 'legacy_bridge', enabledInMvp: true }).map((rule) => ({
    ...rule,
    default_severity: 'warning',
    repair_supported: rule.repair_surfaces.includes('paper_lint'),
    available: BILINGUAL_RULE_IDS.has(rule.rule_id)
      ? Boolean(process.env.SJTU_API_KEY && process.env.SJTU_API_BASE_URL && process.env.SJTU_API_MODEL)
      : Boolean(process.env.REVIEW_PILOT_DEEPSEEK_API_KEY) && fs.existsSync(path.join(resolveEngineBackendDir(), 'novref', 'domain', 'paper_lint')),
  }));
}

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

function resolvePaperModelPython() {
  return process.env.PAPER_MODEL_PYTHON
    || process.env.FIVE_RULE_PYTHON
    || process.env.SIX_RULE_PYTHON
    || 'python3';
}

function runJsonScript(script, args, {
  python,
  cwd,
  timeoutMs = ENGINE_TIMEOUT_MS,
  signal,
  unavailableMessage = '规则脚本无法启动',
} = {}) {
  if (signal?.aborted) return Promise.reject(createHttpError(504, RUN_TIMEOUT_MESSAGE));
  return new Promise((resolve, reject) => {
    const child = spawn(python, [script, ...args], {
      cwd,
      env: childEnvironment(),
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    let outputTooLarge = false;
    const onAbort = () => {
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    };
    signal?.addEventListener('abort', onAbort, { once: true });
    const clearRun = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    };
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
      clearRun();
      reject(signal?.aborted ? createHttpError(504, RUN_TIMEOUT_MESSAGE) : createHttpError(503, unavailableMessage));
    });
    child.once('close', (code) => {
      clearRun();
      if (timedOut || signal?.aborted) return reject(createHttpError(504, RUN_TIMEOUT_MESSAGE));
      if (outputTooLarge) return reject(createHttpError(502, '规则审查结果过大，无法返回'));
      if (code !== 0) return reject(createHttpError(502, parseLastEngineError(stderr) || unavailableMessage));
      try {
        resolve(parseLastEnginePayload(stdout));
      } catch {
        reject(createHttpError(502, '规则脚本返回了无法解析的结果'));
      }
    });
  });
}

function runBridge(args, timeoutMs = ENGINE_TIMEOUT_MS, signal) {
  const backendDir = resolveEngineBackendDir();
  assertEngineAvailable(backendDir);
  return runJsonScript(
    bridgeScript,
    ['--backend-dir', backendDir, ...args],
    {
      python: resolveEnginePython(backendDir),
      cwd: backendDir,
      timeoutMs,
      signal,
      unavailableMessage: 'review-pilot 规则引擎运行失败',
    },
  );
}

function runBilingualSemanticRules(pdfPath, ruleIds, timeoutMs = ENGINE_TIMEOUT_MS, signal) {
  return runJsonScript(
    bilingualScript,
    ['--pdf', pdfPath, ...ruleIds.flatMap((ruleId) => ['--rule', ruleId])],
    {
      python: resolvePaperModelPython(),
      cwd: path.resolve(__dirname, '../..'),
      timeoutMs,
      signal,
      unavailableMessage: '仓库 Paper Model 双语语义规则运行失败',
    },
  );
}

function withRunSlot(callback, signal) {
  return new Promise((resolve, reject) => {
    let queued = false;
    const onAbort = () => {
      if (!queued) return;
      queued = false;
      const index = runQueue.indexOf(start);
      if (index >= 0) runQueue.splice(index, 1);
      reject(createHttpError(504, RUN_TIMEOUT_MESSAGE));
    };
    const start = async () => {
      queued = false;
      signal?.removeEventListener('abort', onAbort);
      if (signal?.aborted) return reject(createHttpError(504, RUN_TIMEOUT_MESSAGE));
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
    if (signal?.aborted) reject(createHttpError(504, RUN_TIMEOUT_MESSAGE));
    else if (activeRunCount < MAX_CONCURRENT_RUNS) start();
    else {
      queued = true;
      runQueue.push(start);
      signal?.addEventListener('abort', onAbort, { once: true });
    }
  });
}

async function getPaperLintCatalog({ refresh = false, mvpOnly = false } = {}) {
  if (mvpOnly) {
    const available = await getLocalRuleAvailability({ refresh });
    return { engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash',
      rules: LOCAL_RULES.filter(rule => rule.enabled_in_mvp).map(rule => ({ ...rule, available })) };
  }
  if (refresh || !catalogPromise || Date.now() >= catalogExpiresAt) {
    catalogExpiresAt = Infinity;
    catalogPromise = (async () => {
      try {
        const localAvailable = await getLocalRuleAvailability({ refresh });
        const localRules = LOCAL_RULES.map((rule) => ({ ...rule, available: localAvailable }));
        return {
          engine: 'sjtu-local',
          mode: 'pdf_lint',
          semantic_model: process.env.SJTU_API_MODEL || 'deepseek-v4-flash',
          rules: [...localRules, ...getSixRules(), ...getCompilerRules(), ...enabledLegacyCatalogRules()]
            .filter((rule) => !RETIRED_RULE_IDS.has(rule.rule_id)),
        };
      } catch {
        // A temporary bridge failure must not hide the existing rule catalog indefinitely.
        catalogExpiresAt = 0;
        const localAvailable = await getLocalRuleAvailability({ refresh });
        return {
          engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash',
          rules: LOCAL_RULES.map((rule) => ({ ...rule, available: localAvailable })).concat(getSixRules(), getCompilerRules(), enabledLegacyCatalogRules()),
        };
      }
    })();
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
  const retired = normalized.find((ruleId) => RETIRED_RULE_IDS.has(ruleId));
  if (retired) throw createHttpError(400, `该审查规则已下线：${retired}`);
  const unknown = normalized.find((ruleId) => !knownIds.has(ruleId));
  if (unknown) throw createHttpError(400, `未知的审查规则：${unknown}`);
  const unavailable = catalog.rules.find(
    (rule) => normalized.includes(rule.rule_id) && rule.available === false,
  );
  if (unavailable) {
    throw createHttpError(503, `${unavailable.title || unavailable.rule_id}暂不可用，请联系管理员配置检测服务`);
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
  const mvpOnly = Array.isArray(selectedRuleIds) && selectedRuleIds.every(id =>
    LOCAL_RULES.some(rule => rule.rule_id === String(id).trim() && rule.enabled_in_mvp));
  const catalog = await getPaperLintCatalog({ mvpOnly });
  const normalized = validateSelectedRuleIds(catalog, selectedRuleIds);
  validateExternalProcessingConsent(catalog, normalized, externalProcessingConsent);
  return normalized;
}

function mergePaperLintResults(existingResult, localResult, selectedRuleIds) {
  const runsById = new Map([...existingResult.rule_runs, ...localResult.rule_runs].map((run) => [run.rule_id, run]));
  const ruleRuns = selectedRuleIds.map((ruleId) => {
    const run = runsById.get(ruleId);
    if (!run) throw createHttpError(502, `规则 ${ruleId} 没有返回检测结果`);
    return run;
  });
  const compilerVersions = [...new Set(ruleRuns.filter(run => isCompilerRuleId(run.rule_id))
    .map(run => run.runtime_version || run.pipeline_version).filter(Boolean))];
  return {
    ...existingResult,
    runtime: ruleRuns.find(run => run.runtime_snapshot)?.runtime_snapshot || existingResult.runtime || null,
    ruleset: { id: 'smart-degree-combined-pdf-lint', name: '基础规则检测',
      version_number: 1, version_label: '当前本地版本' + (compilerVersions.length ? ` · 引用规则 ${compilerVersions.join('、')}` : '') },
    rule_runs: ruleRuns,
    summary: summarizeRuleRuns(ruleRuns),
  };
}

async function runPaperLint({ pdfBuffer, selectedRuleIds, externalProcessingConsent = false, background = false, onProgress }) {
  validatePdf(pdfBuffer);
  // The deadline covers catalog loading, queueing, and both engines so a timed-out
  // browser request cannot later persist a seemingly successful report.
  const includesSixRules = Array.isArray(selectedRuleIds) &&
    selectedRuleIds.some(ruleId => (isSixRuleId(String(ruleId).trim()) || isCompilerRuleId(String(ruleId).trim())));
  const includesLongLlmRule = Array.isArray(selectedRuleIds) && selectedRuleIds.some(ruleId => String(ruleId).trim() === 'typo_detection_check');
  const maximumTimeout = background || includesSixRules || includesLongLlmRule ? SIX_RULE_TIMEOUT_MS : ENGINE_TIMEOUT_MS;
  const requestedTimeout = Number(process.env.PAPER_LINT_RUN_TIMEOUT_MS);
  const timeoutMs = Number.isFinite(requestedTimeout) && requestedTimeout > 0
    ? Math.min(requestedTimeout, maximumTimeout) : maximumTimeout;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const normalizedRuleIds = await normalizeSelectedRuleIds(selectedRuleIds, externalProcessingConsent);
    if (controller.signal.aborted) throw createHttpError(504, RUN_TIMEOUT_MESSAGE);
    return await withRunSlot(async () => {
      const tempDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'smart-degree-paper-lint-'));
      const pdfPath = path.join(tempDir, 'input.pdf');
      try {
        if (controller.signal.aborted) throw createHttpError(504, RUN_TIMEOUT_MESSAGE);
        await fs.promises.writeFile(pdfPath, pdfBuffer, { flag: 'wx', mode: 0o600 });
        const bilingualRuleIds = normalizedRuleIds.filter((ruleId) => BILINGUAL_RULE_IDS.has(ruleId));
        const otherRuleIds = normalizedRuleIds.filter((ruleId) => !BILINGUAL_RULE_IDS.has(ruleId));
        const completedRuleIds = [];
        const completedRuns = [];
        const parts = [];
        const tasks = [];
        const reportProgress = async (ruleIds, result) => {
          completedRuleIds.push(...ruleIds);
          if (Array.isArray(result?.rule_runs)) completedRuns.push(...result.rule_runs);
          if (typeof onProgress === 'function') await onProgress({ completed_rule_ids: [...completedRuleIds], total_rule_ids: normalizedRuleIds, rule_runs: [...completedRuns] });
        };
        if (bilingualRuleIds.length) {
          tasks.push(runBilingualSemanticRules(pdfPath, bilingualRuleIds, ENGINE_TIMEOUT_MS, controller.signal)
            .then(async (part) => { parts.push(part); await reportProgress(bilingualRuleIds, part); }));
        }
        if (otherRuleIds.length) {
          tasks.push(runPaperLintRuleGroups({
            pdfPath,
            selectedRuleIds: otherRuleIds,
            signal: controller.signal,
            onGroupComplete: async ({ ruleIds, result }) => reportProgress(ruleIds, result),
            runners: {
              local_pdf: (file, ruleIds, options) => runLocalFiveRules(file, ruleIds, options),
              six_pdf: (file, ruleIds, options) => runSixRules(file, ruleIds, options),
              compiler: (file, ruleIds, options) => runCompilerRules(file, ruleIds, options),
              legacy_bridge: (_file, ruleIds, { signal }) => runBridge([
                '--pdf', pdfPath, ...ruleIds.flatMap((ruleId) => ['--rule', ruleId]),
              ], ENGINE_TIMEOUT_MS, signal),
            },
          }).then((groupResults) => parts.push(...groupResults)));
        }
        await Promise.all(tasks);
        if (controller.signal.aborted) throw createHttpError(504, RUN_TIMEOUT_MESSAGE);
        const result = parts.length > 1
          ? mergePaperLintResults(parts[0], { rule_runs: parts.slice(1).flatMap((part) => part.rule_runs) }, normalizedRuleIds)
          : parts[0];
        return { result, selectedRuleIds: normalizedRuleIds };
      } finally {
        await fs.promises.rm(tempDir, { recursive: true, force: true });
      }
    }, controller.signal);
  } catch (error) {
    if (!controller.signal.aborted) throw error;
    const timeout = createHttpError(504, RUN_TIMEOUT_MESSAGE);
    timeout.code = 'PAPER_LINT_TIMEOUT';
    timeout.details = { kind: 'run_timeout', timeout_ms: timeoutMs };
    if (typeof error.code === 'string' && error.code.startsWith('DETECTOR_')) {
      timeout.details.detector = error.details;
    }
    throw timeout;
  } finally {
    clearTimeout(timer);
  }
}

module.exports = {
  MAX_PDF_BYTES,
  getPaperLintCatalog,
  mergePaperLintResults,
  runPaperLint,
  resolveEngineBackendDir,
  validateExternalProcessingConsent,
  validateSelectedRuleIds,
  validatePdf,
  normalizeSelectedRuleIds,
};
