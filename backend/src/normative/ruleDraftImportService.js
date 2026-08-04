const { assertRuleConfigAccess } = require('./ruleConfigService');
const ruleDraftRepository = require('./ruleDraftRepository');

const MAX_RULE_DRAFT_IMPORT_BYTES = 1024 * 1024;
const ALLOWED_TEMPLATE_SEVERITIES = Object.freeze(['严重', '一般', '轻微']);
const REQUIRED_TEMPLATE_FIELDS = Object.freeze(['rule_id', 'title', 'category', 'severity', 'enabled', 'message']);

function createRuleDraftImportNotImplementedError() {
  const error = new Error('规则草稿导入服务尚未实现');
  error.code = 'RULE_DRAFT_IMPORT_NOT_IMPLEMENTED';
  return error;
}

async function importRuleDraftTemplate(user, upload = {}) {
  assertRuleConfigAccess(user, upload.scope || {});
  void ruleDraftRepository;
  void MAX_RULE_DRAFT_IMPORT_BYTES;
  void ALLOWED_TEMPLATE_SEVERITIES;
  void REQUIRED_TEMPLATE_FIELDS;
  throw createRuleDraftImportNotImplementedError();
}

module.exports = {
  MAX_RULE_DRAFT_IMPORT_BYTES,
  ALLOWED_TEMPLATE_SEVERITIES,
  REQUIRED_TEMPLATE_FIELDS,
  importRuleDraftTemplate,
};
