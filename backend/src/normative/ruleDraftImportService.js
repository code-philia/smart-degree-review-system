const { assertRuleConfigAccess } = require('./ruleConfigService');
const ruleDraftRepository = require('./ruleDraftRepository');

const MAX_RULE_DRAFT_IMPORT_BYTES = 1024 * 1024;
const ALLOWED_TEMPLATE_SEVERITIES = Object.freeze(['严重', '一般', '轻微']);
const REQUIRED_TEMPLATE_FIELDS = Object.freeze(['rule_id', 'title', 'category', 'severity', 'enabled', 'message']);

function createHttpError(status, message, extra = {}) {
  const error = new Error(message);
  error.status = status;
  Object.assign(error, extra);
  return error;
}

function resolveScope(user, requestedScope = {}) {
  const requestedCollegeId = requestedScope.college_id || requestedScope.collegeId || null;
  if (requestedScope.level === 'college' || requestedCollegeId || user?.role === 'COLLEGE_ADMIN') {
    return { level: 'college', college_id: requestedCollegeId || user?.collegeId };
  }
  return { level: 'school' };
}

function rejectUnsupportedUpload(upload = {}) {
  const fileName = String(upload.fileName || '').toLowerCase();
  const contentType = String(upload.contentType || '').toLowerCase();
  if (fileName.endsWith('.doc') || fileName.endsWith('.docx') || contentType.includes('wordprocessingml') || contentType.includes('msword')) {
    throw createHttpError(400, 'DOC/DOCX 模板不支持自动推导规则');
  }
  if (contentType && !contentType.includes('application/json') && !contentType.includes('text/json') && !contentType.includes('octet-stream')) {
    throw createHttpError(400, '请上传 UTF-8 JSON 规则集文件');
  }
}

function readUploadText(upload = {}) {
  const content = upload.content;
  const buffer = Buffer.isBuffer(content) ? content : Buffer.from(String(content || ''), 'utf8');
  if (buffer.byteLength > MAX_RULE_DRAFT_IMPORT_BYTES) {
    throw createHttpError(413, '文件大小不能超过 1 MB');
  }
  return buffer.toString('utf8');
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function validateRuleItem(item, itemIndex) {
  const errors = [];
  if (!isPlainObject(item)) {
    return [{ item_index: itemIndex, field: 'item', reason: '规则项必须为对象' }];
  }

  for (const field of REQUIRED_TEMPLATE_FIELDS) {
    if (item[field] === undefined || item[field] === null || item[field] === '') {
      errors.push({ item_index: itemIndex, field, reason: `${field} 缺失` });
    }
  }

  if (item.severity !== undefined && !ALLOWED_TEMPLATE_SEVERITIES.includes(item.severity)) {
    errors.push({ item_index: itemIndex, field: 'severity', reason: 'severity 必须为严重、一般、轻微' });
  }
  if (item.enabled !== undefined && typeof item.enabled !== 'boolean') {
    errors.push({ item_index: itemIndex, field: 'enabled', reason: 'enabled 必须为布尔值' });
  }
  if (item.params !== undefined && !isPlainObject(item.params)) {
    errors.push({ item_index: itemIndex, field: 'params', reason: 'params 必须为 JSON 对象' });
  }

  return errors;
}

function normalizeRuleItem(item) {
  return {
    rule_id: String(item.rule_id),
    title: String(item.title),
    category: String(item.category),
    severity: item.severity,
    enabled: item.enabled,
    message: String(item.message),
    params: item.params || {},
  };
}

async function importRuleDraftTemplate(user, upload = {}) {
  const scope = resolveScope(user, upload.scope || {});
  assertRuleConfigAccess(user, scope);
  rejectUnsupportedUpload(upload);

  let parsed;
  try {
    parsed = JSON.parse(readUploadText(upload));
  } catch (error) {
    throw createHttpError(400, 'JSON 文件解析失败，请确认文件为 UTF-8 JSON 数组');
  }

  if (!Array.isArray(parsed)) {
    throw createHttpError(400, 'JSON 顶层必须为数组', {
      errors: [{ item_index: null, field: 'root', reason: 'JSON 顶层必须为数组' }],
    });
  }

  const errors = parsed.flatMap((item, index) => validateRuleItem(item, index));
  if (errors.length > 0) {
    throw createHttpError(400, errors.map((entry) => `第 ${entry.item_index} 项 ${entry.reason}`).join('；'), { errors });
  }

  const normalizedDrafts = parsed.map(normalizeRuleItem);
  const updatedBy = user.id || user.username || 'unknown';
  const result = await ruleDraftRepository.replaceRuleDrafts(scope, normalizedDrafts, updatedBy);

  return {
    scope,
    imported_count: result.created,
    draft_batch_id: result.draft_batch_id,
    drafts: result.drafts.map((draft) => ({
      rule_id: draft.rule_id,
      title: draft.title,
      category: draft.category,
      severity: draft.severity,
      enabled: draft.enabled,
    })),
  };
}

module.exports = {
  MAX_RULE_DRAFT_IMPORT_BYTES,
  ALLOWED_TEMPLATE_SEVERITIES,
  REQUIRED_TEMPLATE_FIELDS,
  importRuleDraftTemplate,
};
