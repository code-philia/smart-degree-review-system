const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { Transform } = require('stream');
const { pipeline } = require('stream/promises');
const { summarizeRuleRuns } = require('./localFiveRulePaperLintService');
const { listRuleDefinitions } = require('../../rules/registry');

const SCRIPT = path.resolve(__dirname, '../../scripts/six_rule_detector.py');
const DEFAULT_TIMEOUT_MS = 20 * 60 * 1000;
// Report bytes go to disk with backpressure. This resource ceiling is distinct
// from execFile's old 30MiB cap shared by legitimate JSON and diagnostic stderr.
const DEFAULT_OUTPUT_BYTES = 256 * 1024 * 1024;
const STDERR_CAPTURE_BYTES = 64 * 1024;
const DEFINITIONS = listRuleDefinitions({ family: 'six_pdf' });
const CLOUD_IDS = new Set(DEFINITIONS.filter((rule) => rule.availability_probe === 'mineru').map((rule) => rule.rule_id));
const RULE_IDS = new Set(DEFINITIONS.map((rule) => rule.rule_id));

function getSixRules() {
  return DEFINITIONS.map((rule) => ({
    ...rule,
    default_severity: 'warning',
    repair_supported: rule.repair_surfaces.includes('paper_lint'),
    available: !CLOUD_IDS.has(rule.rule_id) || Boolean(process.env.MINERU_API_TOKEN),
    source: 'sjtu-six-pdf',
  }));
}

function isSixRuleId(ruleId) {
  return RULE_IDS.has(ruleId);
}

function toSixRuleResult(output, selectedRuleIds) {
  const ruleRuns = selectedRuleIds.map((ruleId) => {
    if (!RULE_IDS.has(ruleId)) throw new Error('未知六规则：' + ruleId);
    const number = Number(ruleId.slice('sjtu_rule_'.length));
    const raw = output?.rules?.[String(number)];
    if (!raw || !['completed', 'unsupported'].includes(raw.status) || !Array.isArray(raw.findings)) {
      const error = new Error('规则 ' + number + ' 检测器结果不完整');
      error.status = 502;
      throw error;
    }
    const findings = raw.findings.map((item, index) => {
      if (item.location?.type !== 'pdf_bbox' || !item.location.bounding_rect) {
        const error = new Error('规则 ' + number + ' 第 ' + (index + 1) + ' 处发现缺少 PDF 坐标');
        error.status = 502;
        throw error;
      }
      return {
        finding_id: ruleId + '_' + (index + 1), rule_id: ruleId, message: item.message,
        suggestion: '请对照 PDF 原文核查该处，并按论文规范修订。',
        location: item.location, anchors: [],
      };
    });
    return {
      rule_run_id: 'run_' + ruleId, rule_id: ruleId, severity: 'warning', params: null,
      execution_status: raw.status,
      evidence_mode: raw.status === 'completed' ? 'native' : 'unsupported',
      outcome: raw.status === 'unsupported' ? 'inconclusive' : findings.length ? 'issues_found' : 'passed',
      message: raw.reason || null, findings,
    };
  });
  return {
    type: 'paper_lint', paper_title: '上传论文',
    ruleset: { id: 'sjtu-six-rule-pdf', name: '上交大六规则', version_number: 1,
      version_label: '六规则' },
    rule_runs: ruleRuns, summary: summarizeRuleRuns(ruleRuns),
  };
}

function stderrDiagnostic(tail) {
  const text = tail.toString('utf8');
  const frames = [];
  for (const match of text.matchAll(/^\s*File "([^"\n]+)", line (\d+), in ([A-Za-z0-9_<>]+)\s*$/gm)) {
    const file = path.basename(match[1]).replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 80);
    if (file.endsWith('.py')) frames.push({ file, line: Number(match[2]), function: match[3].slice(0, 80) });
  }
  const exceptions = [...text.matchAll(/^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):/gm)];
  return {
    stderr_frames: frames.slice(-8),
    stderr_exception_type: exceptions.at(-1)?.[1].slice(0, 80) || null,
    missing_pymupdf: /No module named ['"]?pymupdf\b/.test(text),
  };
}

function detectorFailure(kind, details) {
  const definitions = {
    unavailable: ['DETECTOR_UNAVAILABLE', 503, '六规则检测器不可用：请配置 SIX_RULE_PYTHON 并安装 backend/requirements-six-rule-detector.txt'],
    timeout: ['DETECTOR_TIMEOUT', 504, '六规则检测超时'],
    aborted: ['DETECTOR_ABORTED', 504, '六规则检测已取消'],
    process_signal: ['DETECTOR_SIGNALLED', 502, '六规则检测器被系统信号终止'],
    process_exit: ['DETECTOR_EXIT_NONZERO', 502, '六规则检测器异常退出'],
    output_limit: ['DETECTOR_OUTPUT_LIMIT', 502, '六规则检测器输出超过本次资源上限'],
    invalid_json: ['DETECTOR_INVALID_JSON', 502, '六规则检测器返回了无法解析的结果'],
    io_error: ['DETECTOR_IO_ERROR', 502, '六规则检测临时文件不可用'],
  };
  const [code, status, message] = definitions[kind];
  const suffix = kind === 'process_exit' ? `（退出码 ${details.exit_code}）`
    : kind === 'process_signal' ? `（${details.signal}）` : '';
  const failure = new Error(message + suffix);
  if (kind === 'aborted') failure.name = 'AbortError';
  failure.code = code;
  failure.status = status;
  // Never attach raw stderr, arguments, an AbortSignal reason or an error cause.
  // API credentials and signed download URLs can occur in any of those strings.
  failure.details = { ...details, kind };
  return failure;
}

async function detectorOutput(python, args, { signal, timeoutMs, killGraceMs, maxStdoutBytes }) {
  const started = performance.now();
  const details = { timeout_ms: timeoutMs, max_stdout_bytes: maxStdoutBytes,
    exit_code: null, signal: null, spawn_code: null, stdout_bytes: 0, stderr_bytes: 0 };
  if (signal?.aborted) throw detectorFailure('aborted', details);
  const tempRoot = process.env.SIX_RULE_TEMP_DIR ||
    (process.platform === 'win32' ? os.tmpdir() : '/data/tmp/six-rule-detector');
  let directory;
  let child;
  let reason = null;
  let spawnError = null;
  let stderrTail = Buffer.alloc(0);
  let timer;
  let termination;
  const posix = process.platform !== 'win32';
  function groupExists() {
    if (!child?.pid) return false;
    try { process.kill(posix ? -child.pid : child.pid, 0); return true; }
    catch (error) { return error.code !== 'ESRCH'; }
  }
  function kill(signalName) {
    if (!child?.pid) return;
    try {
      if (posix) process.kill(-child.pid, signalName);
      else child.kill(signalName);
    } catch (error) { if (error.code !== 'ESRCH') details.kill_code = error.code; }
  }
  function terminate() {
    if (termination) return termination;
    kill('SIGTERM');
    termination = groupExists()
      ? new Promise(resolve => setTimeout(() => { kill('SIGKILL'); resolve(); }, killGraceMs))
      : Promise.resolve();
    return termination;
  }
  function abort() { reason ||= 'aborted'; terminate(); }
  try {
    await fs.promises.mkdir(tempRoot, { recursive: true, mode: 0o700 });
    directory = await fs.promises.mkdtemp(path.join(tempRoot, 'run-'));
    const outputFile = path.join(directory, 'stdout.json');
    if (signal?.aborted) throw detectorFailure('aborted', details);
    child = spawn(python, args, {
      windowsHide: true, detached: posix, stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    child.stderr.on('data', chunk => {
      details.stderr_bytes += chunk.length;
      stderrTail = chunk.length >= STDERR_CAPTURE_BYTES
        ? Buffer.from(chunk.subarray(chunk.length - STDERR_CAPTURE_BYTES))
        : Buffer.concat([stderrTail, chunk]).subarray(-STDERR_CAPTURE_BYTES);
    });
    const closed = new Promise(resolve => {
      child.once('error', error => { spawnError = error; details.spawn_code = error.code || null; });
      child.once('exit', (code, signalName) => {
        details.exit_code = code; details.signal = signalName; terminate();
      });
      child.once('close', resolve);
    });
    let prefixSeen = false;
    const monitor = new Transform({ transform(chunk, _encoding, callback) {
      details.stdout_bytes += chunk.length;
      if (details.stdout_bytes > maxStdoutBytes) {
        reason ||= 'output_limit'; callback(new Error('stdout resource limit')); return;
      }
      if (!prefixSeen) {
        const byte = chunk.find(value => ![9, 10, 13, 32].includes(value));
        if (byte !== undefined) {
          prefixSeen = true;
          if (byte !== 123) {
            reason ||= 'invalid_json'; callback(new Error('stdout is not a report object')); return;
          }
        }
      }
      callback(null, chunk);
    } });
    const outputDone = pipeline(child.stdout, monitor,
      fs.createWriteStream(outputFile, { flags: 'wx', mode: 0o600 })).catch(error => {
      if (!spawnError) { reason ||= 'io_error'; details.io_code = error.code || null; }
      terminate();
    });
    timer = setTimeout(() => { reason ||= 'timeout'; terminate(); }, timeoutMs);
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
    await closed;
    clearTimeout(timer);
    await outputDone;
    await terminate(); // Descendants can outlive a normally exited leader.
    details.elapsed_ms = Math.round(performance.now() - started);
    details.stderr_truncated = details.stderr_bytes > STDERR_CAPTURE_BYTES;
    const diagnostic = stderrDiagnostic(stderrTail);
    details.stderr_frames = diagnostic.stderr_frames;
    details.stderr_exception_type = diagnostic.stderr_exception_type;
    if (spawnError?.code === 'ENOENT' || diagnostic.missing_pymupdf) throw detectorFailure('unavailable', details);
    if (reason) throw detectorFailure(reason, details);
    if (details.signal) throw detectorFailure('process_signal', details);
    if (spawnError || details.exit_code !== 0) throw detectorFailure('process_exit', details);
    try {
      const bytes = await fs.promises.readFile(outputFile);
      return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    } catch { throw detectorFailure('invalid_json', details); }
  } catch (error) {
    if (error.details) throw error;
    details.io_code = error.code || null;
    throw detectorFailure('io_error', details);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
    if (child) await terminate();
    if (directory) await fs.promises.rm(directory, { recursive: true, force: true });
  }
}

async function runSixRules(pdfPath, selectedRuleIds, {
  signal, timeoutMs = DEFAULT_TIMEOUT_MS, killGraceMs = 1000, maxStdoutBytes = DEFAULT_OUTPUT_BYTES,
} = {}) {
  const numbers = selectedRuleIds.map((ruleId) => {
    if (!RULE_IDS.has(ruleId)) throw new Error('未知六规则：' + ruleId);
    return Number(ruleId.slice('sjtu_rule_'.length));
  });
  const python = process.env.SIX_RULE_PYTHON || process.env.FIVE_RULE_PYTHON ||
    process.env.REVIEW_PILOT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  for (const [name, value] of [['timeoutMs', timeoutMs], ['killGraceMs', killGraceMs], ['maxStdoutBytes', maxStdoutBytes]]) {
    if (!Number.isSafeInteger(value) || value < (name === 'killGraceMs' ? 0 : 1) ||
        (name !== 'maxStdoutBytes' && value > 2147483647)) throw new TypeError('Invalid detector execution budget: ' + name);
  }
  const output = await detectorOutput(python, [SCRIPT, '--pdf', pdfPath,
    ...numbers.flatMap((number) => ['--rule', String(number)])], { signal, timeoutMs, killGraceMs, maxStdoutBytes });
  return toSixRuleResult(output, selectedRuleIds);
}

module.exports = { getSixRules, isSixRuleId, runSixRules, toSixRuleResult, CLOUD_IDS,
  SIX_RULE_TIMEOUT_MS: DEFAULT_TIMEOUT_MS };
