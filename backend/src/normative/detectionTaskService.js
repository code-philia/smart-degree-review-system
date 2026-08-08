const { analyzeDefaultNormativeRules } = require('./normativeService');
const { resolveRulesForAnalysis } = require('./ruleConfigService');
const detectionTaskRepository = require('./detectionTaskRepository');

const MAX_DETECTION_TEXT_BYTES = 50 * 1024 * 1024;
const ALLOWED_DETECTION_FILE_EXTENSIONS = Object.freeze(['.txt', '.md', '.pdf']);
const DETECTION_STATUSES = Object.freeze(['pending', 'running', 'completed']);

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getFileExtension(fileName) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

function validateSource(payload) {
  const sourceType = payload.source_type || 'paste';
  if (!['paste', 'file'].includes(sourceType)) {
    throw createHttpError(400, '检测来源类型无效');
  }

  const sourceFilename = typeof payload.source_filename === 'string' && payload.source_filename.trim()
    ? payload.source_filename.trim()
    : null;

  if (sourceType === 'file') {
    if (!sourceFilename) {
      throw createHttpError(400, '文件检测需要提供文件名');
    }
    if (!ALLOWED_DETECTION_FILE_EXTENSIONS.includes(getFileExtension(sourceFilename))) {
      throw createHttpError(400, '仅支持上传 .txt、.md 或 .pdf 文件');
    }
  }

  return { sourceType, sourceFilename };
}

async function createDetectionTask(user, payload = {}) {
  if (!user) {
    throw createHttpError(401, '请先登录后发起规范检测');
  }

  const text = typeof payload.text === 'string' ? payload.text : '';
  if (!text.trim()) {
    throw createHttpError(400, '检测文本不能为空');
  }
  if (Buffer.byteLength(text, 'utf8') > MAX_DETECTION_TEXT_BYTES) {
    throw createHttpError(413, '检测文本或文件内容不能超过 50 MB');
  }

  const { sourceType, sourceFilename } = validateSource(payload);
  const rules = await resolveRulesForAnalysis({ college_id: user.collegeId });
  const analysis = await analyzeDefaultNormativeRules(text);
  const issues = Array.isArray(analysis.issues) ? analysis.issues : [];
  const severityCounts = issues.reduce((counts, issue) => {
    counts[issue.severity] = (counts[issue.severity] || 0) + 1;
    return counts;
  }, {});

  return detectionTaskRepository.createDetectionTask({
    user_id: user.username || user.id,
    status: 'completed',
    source_type: sourceType,
    source_filename: sourceFilename,
    original_text: text,
    rule_snapshot: rules,
    issues,
    severity_counts: severityCounts,
  });
}

module.exports = {
  MAX_DETECTION_TEXT_BYTES,
  ALLOWED_DETECTION_FILE_EXTENSIONS,
  DETECTION_STATUSES,
  createDetectionTask,
};
