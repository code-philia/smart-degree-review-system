const { execFile } = require('child_process');
const path = require('path');
const { promisify } = require('util');
const { summarizeRuleRuns } = require('./localFiveRulePaperLintService');

const execFileAsync = promisify(execFile);
const SCRIPT = path.resolve(__dirname, '../../scripts/six_rule_detector.py');
const DEFINITIONS = [
  [11, '图引用目标不存在', '检查正文引用的图是否有对应图对象或图题。'],
  [13, '图缺少图题', '识别真实图对象并检查附近是否有图题。'],
  [14, '表缺少表题', '识别真实表对象并检查附近是否有表题。'],
  [15, '图未被全文引用', '检查图在全文是否有有效引用。'],
  [16, '表未被全文引用', '检查表在全文是否有有效引用。'],
  [29, '附录引用目标不存在', '检查附录引用能否找到对应附录。'],
];
const CLOUD_IDS = new Set(['sjtu_rule_13', 'sjtu_rule_14']);
const RULE_IDS = new Set(DEFINITIONS.map(([number]) => 'sjtu_rule_' + number));

function getSixRules() {
  return DEFINITIONS.map(([number, title, description]) => ({
    number, rule_id: 'sjtu_rule_' + number, title: '规则 ' + number + ' · ' + title, description,
    default_severity: 'warning', default_enabled: false,
    execution_mode: 'deterministic', uses_external_model: false,
    available: ![13, 14].includes(number) || Boolean(process.env.MINERU_API_TOKEN),
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

async function runSixRules(pdfPath, selectedRuleIds, { signal } = {}) {
  const numbers = selectedRuleIds.map((ruleId) => {
    if (!RULE_IDS.has(ruleId)) throw new Error('未知六规则：' + ruleId);
    return Number(ruleId.slice('sjtu_rule_'.length));
  });
  const python = process.env.SIX_RULE_PYTHON || process.env.FIVE_RULE_PYTHON ||
    process.env.REVIEW_PILOT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  let stdout;
  try {
    ({ stdout } = await execFileAsync(python, [SCRIPT, '--pdf', pdfPath,
      ...numbers.flatMap((number) => ['--rule', String(number)])], {
      windowsHide: true, timeout: selectedRuleIds.some((id) => CLOUD_IDS.has(id))
        ? 20 * 60 * 1000 : 5 * 60 * 1000,
      maxBuffer: 30 * 1024 * 1024, encoding: 'utf8',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, signal,
    }));
  } catch (error) {
    const unavailable = error.code === 'ENOENT' || /No module named ['"]?pymupdf/.test(error.stderr || '');
    const failure = new Error(unavailable
      ? '六规则检测器不可用：请配置 SIX_RULE_PYTHON 并安装 backend/requirements-six-rule-detector.txt'
      : '六规则检测失败，请检查 PDF 或服务器日志');
    failure.status = unavailable ? 503 : error.killed || error.name === 'AbortError' ? 504 : 502;
    throw failure;
  }
  let output;
  try {
    output = JSON.parse(stdout);
  } catch {
    const error = new Error('六规则检测器返回了无法解析的结果');
    error.status = 502;
    throw error;
  }
  return toSixRuleResult(output, selectedRuleIds);
}

module.exports = { getSixRules, isSixRuleId, runSixRules, toSixRuleResult, CLOUD_IDS };

