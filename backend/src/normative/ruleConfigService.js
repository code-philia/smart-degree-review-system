const { DEFAULT_NORMATIVE_RULES } = require('./normativeService');
const ruleConfigRepository = require('./ruleConfigRepository');

const MANAGE_RULE_ROLES = Object.freeze(['SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

function getRequestedCollegeId(requestedScope = {}) {
  return requestedScope.college_id || requestedScope.collegeId || requestedScope.college || null;
}

function assertRuleConfigAccess(user, requestedScope = {}) {
  if (!user || !MANAGE_RULE_ROLES.includes(user.role)) {
    const error = new Error('无权维护规则配置');
    error.status = 403;
    throw error;
  }

  const requestedCollegeId = getRequestedCollegeId(requestedScope);
  if (user.role === 'COLLEGE_ADMIN' && requestedCollegeId && requestedCollegeId !== user.collegeId) {
    const error = new Error('禁止跨学院维护规则配置');
    error.status = 403;
    throw error;
  }
}

async function listEffectiveRuleConfigurations(user, query = {}) {
  assertRuleConfigAccess(user, query);
  void ruleConfigRepository;
  return { rules: DEFAULT_NORMATIVE_RULES, scope: query.scope || null };
}

async function publishRuleConfiguration(user, payload) {
  assertRuleConfigAccess(user, payload);
  const error = new Error('rule configuration publish is not implemented yet');
  error.code = 'RULE_CONFIG_SERVICE_NOT_IMPLEMENTED';
  throw error;
}

async function resetCollegeRuleConfiguration(user, payload) {
  assertRuleConfigAccess(user, payload);
  const error = new Error('college rule reset is not implemented yet');
  error.code = 'RULE_CONFIG_SERVICE_NOT_IMPLEMENTED';
  throw error;
}

async function resolveRulesForAnalysis(context = {}) {
  void context;
  return DEFAULT_NORMATIVE_RULES;
}

module.exports = {
  MANAGE_RULE_ROLES,
  assertRuleConfigAccess,
  listEffectiveRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
  resolveRulesForAnalysis,
};
