const { execFile } = require('child_process');
const path = require('path');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);
const DETECTOR_SCRIPT = path.resolve(__dirname, '../../scripts/five_rule_detector.py');
const FAST_DETECTOR_SCRIPT = path.resolve(__dirname, '../../scripts/fast_local_detector.py');
const { listRuleDefinitions } = require('../../rules/registry');

const LOCAL_RULES = listRuleDefinitions({ family: 'local_pdf' })
  .filter((rule) => rule.exposed_to_legacy_catalog !== false)
  .map((rule) => ({
    ...rule,
    default_severity: 'warning',
    source: 'sjtu-local',
    repair_supported: rule.repair_surfaces.includes('paper_lint'),
    available: true,
  }));
const RULES_BY_ID = new Map(LOCAL_RULES.map((rule) => [rule.rule_id, rule]));
let availabilityPromise = null;

async function getLocalRuleAvailability({ refresh = false } = {}) {
  if (refresh || !availabilityPromise) {
    const python = process.env.FIVE_RULE_PYTHON || process.env.REVIEW_PILOT_PYTHON ||
      (process.platform === 'win32' ? 'python' : 'python3');
    availabilityPromise = execFileAsync(python, ['-c', 'import pymupdf'], {
      windowsHide: true, timeout: 5000, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    }).then(() => true, () => false);
  }
  return availabilityPromise;
}

function isLocalRuleId(ruleId) {
  return RULES_BY_ID.has(ruleId);
}

function summarizeRuleRuns(ruleRuns) {
  const findings = ruleRuns.flatMap((run) => run.findings || []);
  return {
    rule_count: ruleRuns.length,
    completed_rule_count: ruleRuns.filter((run) => run.execution_status === 'completed').length,
    unsupported_rule_count: ruleRuns.filter((run) => run.execution_status === 'unsupported').length,
    error_rule_count: ruleRuns.filter((run) => run.execution_status === 'error').length,
    issue_rule_count: ruleRuns.filter((run) => run.outcome === 'issues_found').length,
    finding_count: findings.length,
    error_finding_count: ruleRuns.filter((run) => run.severity === 'error').reduce((n, run) => n + run.findings.length, 0),
    warning_finding_count: ruleRuns.filter((run) => run.severity === 'warning').reduce((n, run) => n + run.findings.length, 0),
    info_finding_count: ruleRuns.filter((run) => run.severity === 'info').reduce((n, run) => n + run.findings.length, 0),
    derived_rule_count: ruleRuns.filter((run) => run.evidence_mode === 'derived').length,
  };
}

function detectorOutputError(message) {
  const error = new Error(message);
  error.status = 502;
  return error;
}

function toPaperLintResult(detectorOutput, selectedRuleIds) {
  const ruleRuns = selectedRuleIds.map((ruleId) => {
    const rule = RULES_BY_ID.get(ruleId);
    if (!rule) throw new Error(`未知本地规则：${ruleId}`);
    const raw = detectorOutput?.rules?.[String(rule.number)];
    if (!raw || !['completed', 'unsupported'].includes(raw.status) || !Array.isArray(raw.findings)) {
      throw detectorOutputError(`规则 ${rule.number} 检测器结果不完整`);
    }
    const findings = raw.findings.map((item, index) => {
      const location = item.location?.type === 'pdf_bbox' && item.location.bounding_rect
        ? item.location
        : Number.isSafeInteger(Number(item.location?.page_number || item.page)) && Number(item.location?.page_number || item.page) > 0
          ? { type: 'pdf_page', page_number: Number(item.location?.page_number || item.page), text_excerpt: item.text_excerpt || null }
          : null;
      return {
        finding_id: `${ruleId}_${index + 1}`,
        rule_id: ruleId,
        message: item.message,
        suggestion: item.suggestion || '请对照 PDF 原文核查该处，并按论文规范修订。',
        location,
        anchors: [],
      };
    });
    return {
      rule_run_id: `run_${ruleId}`,
      rule_id: ruleId,
      severity: rule.default_severity,
      params: null,
      execution_status: raw.status,
      evidence_mode: raw.status === 'completed' ? 'native' : 'unsupported',
      outcome: raw.status === 'unsupported' ? 'inconclusive' : findings.length ? 'issues_found' : 'passed',
      message: raw.reason || null,
      findings,
    };
  });
  return {
    type: 'paper_lint',
    paper_title: '上传论文',
    ruleset: { id: 'sjtu-four-rule-pdf', name: '上交大本地四规则', version_number: 1, version_label: '本地四规则' },
    rule_runs: ruleRuns,
    summary: summarizeRuleRuns(ruleRuns),
  };
}

async function runLocalFiveRules(pdfPath, selectedRuleIds, { signal } = {}) {
  const numbers = selectedRuleIds.map((ruleId) => {
    const rule = RULES_BY_ID.get(ruleId);
    if (!rule) throw new Error(`未知本地规则：${ruleId}`);
    return rule.number;
  });
  const python = process.env.FIVE_RULE_PYTHON || process.env.REVIEW_PILOT_PYTHON ||
    (process.platform === 'win32' ? 'python' : 'python3');
  let stdout;
  try {
    ({ stdout } = await execFileAsync(python, [numbers.some(number => [31, 34, 35, 36, 37, 38].includes(number)) ? FAST_DETECTOR_SCRIPT : DETECTOR_SCRIPT, '--pdf', pdfPath,
      ...numbers.flatMap((number) => ['--rule', String(number)])], {
      windowsHide: true, timeout: 300000, maxBuffer: 30 * 1024 * 1024, encoding: 'utf8',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, signal,
    }));
  } catch (error) {
    const unavailable = error.code === 'ENOENT' || /No module named ['"]?pymupdf/.test(error.stderr || '');
    const invalidPdf = !unavailable && /cannot open|cannot recognize|syntax error|document stream|malformed|invalid pdf|failed to open|no objects found|filedataerror/i.test(error.stderr || '');
    const failure = new Error(invalidPdf
      ? 'PDF 文件无效或无法解析，请重新上传'
      : unavailable
        ? '本地四规则检测器不可用：请配置 FIVE_RULE_PYTHON 并安装 backend/requirements-five-rule-detector.txt'
        : '本地四规则检测失败，请检查 PDF 或服务器日志');
    if (invalidPdf) failure.code = 'INVALID_PDF';
    failure.status = unavailable ? 503 : error.killed || error.name === 'AbortError' ? 504 : 502;
    throw failure;
  }
  let output;
  try {
    output = JSON.parse(stdout);
  } catch {
    const error = new Error('本地四规则检测器返回了无法解析的结果');
    error.status = 502;
    throw error;
  }
  return toPaperLintResult(output, selectedRuleIds);
}

module.exports = { LOCAL_RULES, getLocalRuleAvailability, isLocalRuleId, runLocalFiveRules, summarizeRuleRuns, toPaperLintResult };
