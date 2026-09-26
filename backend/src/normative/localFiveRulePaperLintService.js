const { execFile } = require('child_process');
const path = require('path');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);
const DETECTOR_SCRIPT = path.resolve(__dirname, '../../scripts/five_rule_detector.py');
const LOCAL_RULES = [
  { number: 18, title: '规则 18 · 公式引用目标不存在', description: '检查公式引用能否找到对应的可见公式编号。' },
  { number: 22, title: '规则 22 · 文献引用目标不存在', description: '检查全文引用编号能否找到对应参考文献。' },
  { number: 24, title: '规则 24 · 参考文献未被全文引用', description: '检查参考文献是否在正文、附录或图表题等全文位置被引用；发现需人工复核。' },
  { number: 28, title: '规则 28 · 目录页码与正文不一致', description: '检查目录条目的页码与正文标题位置是否一致。' },
].map(({ number, title, description }) => ({
  number,
  rule_id: `sjtu_rule_${number}`,
  title,
  description,
  default_severity: 'warning',
  default_enabled: false,
  execution_mode: 'deterministic',
  uses_external_model: false,
  available: true,
  source: 'sjtu-local',
}));
const RULES_BY_ID = new Map(LOCAL_RULES.map((rule) => [rule.rule_id, rule]));

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
      if (item.location?.type !== 'pdf_bbox' || !item.location.bounding_rect) {
        throw detectorOutputError(`规则 ${rule.number} 第 ${index + 1} 处发现缺少 PDF 坐标`);
      }
      return {
        finding_id: `${ruleId}_${index + 1}`,
        rule_id: ruleId,
        message: item.message,
        suggestion: '请对照 PDF 原文核查该处，并按论文规范修订。',
        location: item.location,
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
    ({ stdout } = await execFileAsync(python, [DETECTOR_SCRIPT, '--pdf', pdfPath,
      ...numbers.flatMap((number) => ['--rule', String(number)])], {
      windowsHide: true, timeout: 300000, maxBuffer: 30 * 1024 * 1024, encoding: 'utf8',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, signal,
    }));
  } catch (error) {
    const unavailable = error.code === 'ENOENT' || /No module named ['"]?pymupdf/.test(error.stderr || '');
    const failure = new Error(unavailable
      ? '本地四规则检测器不可用：请配置 FIVE_RULE_PYTHON 并安装 backend/requirements-five-rule-detector.txt'
      : '本地四规则检测失败，请检查 PDF 或服务器日志');
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

module.exports = { LOCAL_RULES, isLocalRuleId, runLocalFiveRules, summarizeRuleRuns, toPaperLintResult };