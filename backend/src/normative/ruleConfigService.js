const { DEFAULT_NORMATIVE_RULES } = require('./normativeService');
const ruleConfigRepository = require('./ruleConfigRepository');

const MANAGE_RULE_ROLES = Object.freeze(['SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getRequestedCollegeId(requestedScope = {}) {
  return requestedScope.college_id || requestedScope.collegeId || requestedScope.college || null;
}

function getScopeFromPayload(payload = {}) {
  if (payload.scope && typeof payload.scope === 'object') {
    return { ...payload.scope, college_id: getRequestedCollegeId(payload.scope) || getRequestedCollegeId(payload) };
  }
  return payload;
}

function assertRuleConfigAccess(user, requestedScope = {}) {
  if (!user || !MANAGE_RULE_ROLES.includes(user.role)) {
    throw createHttpError(403, '无权维护规则配置');
  }

  const requestedCollegeId = getRequestedCollegeId(requestedScope);
  if (user.role === 'COLLEGE_ADMIN' && requestedCollegeId && requestedCollegeId !== user.collegeId) {
    throw createHttpError(403, '禁止跨学院维护规则配置');
  }
}

function normalizeScope(user, inputScope = {}) {
  const scope = getScopeFromPayload(inputScope);
  const requestedLevel = scope.level || scope.scope_level;
  const collegeId = getRequestedCollegeId(scope);

  if (requestedLevel === 'college' || collegeId || user?.role === 'COLLEGE_ADMIN') {
    const resolvedCollegeId = collegeId || user?.collegeId;
    if (!resolvedCollegeId) {
      throw createHttpError(400, '学院规则配置需要 college_id');
    }
    return { level: 'college', college_id: resolvedCollegeId };
  }

  return { level: 'school' };
}

function normalizeDefaultRule(rule) {
  const isTextLongSentence = rule.rule_id === 'TEXT-LONG-SENTENCE' || rule.rule_id === 'NORM-006';
  return {
    rule_id: isTextLongSentence ? 'TEXT-LONG-SENTENCE' : rule.rule_id,
    title: isTextLongSentence ? '长句字符阈值' : rule.title,
    category: rule.category,
    severity: rule.severity || (isTextLongSentence ? 'medium' : 'medium'),
    enabled: rule.enabled !== false,
    match_params: rule.match_params || (isTextLongSentence ? { max_chars: 120 } : {}),
    prompt: rule.prompt || rule.title,
    source: 'national',
    college_id: null,
  };
}

function normalizeOverrideRule(override, source) {
  return {
    rule_id: override.rule_id,
    title: override.title,
    category: override.category,
    severity: override.severity,
    enabled: Boolean(override.enabled),
    match_params: override.match_params || {},
    prompt: override.prompt,
    source,
    college_id: override.college_id || null,
  };
}

function applyOverrides(baseRules, overrides, source) {
  const byRuleId = new Map(baseRules.map((rule) => [rule.rule_id, rule]));
  overrides.forEach((override) => {
    byRuleId.set(override.rule_id, normalizeOverrideRule(override, source));
  });
  return Array.from(byRuleId.values()).sort((left, right) => left.rule_id.localeCompare(right.rule_id));
}

async function getMergedRules(scope = {}) {
  const schoolOverrides = await ruleConfigRepository.listRuleOverrides({ level: 'school' });
  let rules = applyOverrides(DEFAULT_NORMATIVE_RULES.map(normalizeDefaultRule), schoolOverrides, 'school');

  if (scope.level === 'college') {
    const collegeOverrides = await ruleConfigRepository.listRuleOverrides({ level: 'college', college_id: scope.college_id });
    rules = applyOverrides(rules, collegeOverrides, 'college');
  }

  return rules;
}

function normalizePublishRule(rule = {}) {
  if (!rule.rule_id || !rule.title) {
    throw createHttpError(400, '规则配置缺少 rule_id 或标题');
  }

  return {
    rule_id: rule.rule_id,
    title: rule.title,
    category: rule.category || '文本质量',
    severity: rule.severity || 'medium',
    enabled: rule.enabled !== false,
    match_params: rule.match_params || {},
    prompt: rule.prompt || rule.title,
  };
}

async function listEffectiveRuleConfigurations(user, query = {}) {
  const scope = normalizeScope(user, query);
  assertRuleConfigAccess(user, scope);
  const rules = await getMergedRules(scope);
  return { scope, rules };
}

async function publishRuleConfiguration(user, payload = {}) {
  const scope = normalizeScope(user, payload);
  assertRuleConfigAccess(user, scope);
  const rule = normalizePublishRule(payload.rule || payload);

  await ruleConfigRepository.upsertRuleOverride(
    { level: scope.level, college_id: scope.college_id },
    { ...rule, updated_by: user.id || user.username || 'unknown' },
  );

  const rules = await getMergedRules(scope);
  return { scope, rules };
}

async function resetCollegeRuleConfiguration(user, payload = {}) {
  const scope = normalizeScope(user, { level: 'college', ...payload });
  assertRuleConfigAccess(user, scope);
  const ruleId = payload.rule_id || payload.ruleId;
  if (!ruleId) {
    throw createHttpError(400, '学院重置需要 rule_id');
  }

  await ruleConfigRepository.deleteRuleOverride({ level: 'college', college_id: scope.college_id, rule_id: ruleId });
  const rules = await getMergedRules(scope);
  return { scope, rules };
}

async function resolveRulesForAnalysis(context = {}) {
  const collegeId = getRequestedCollegeId(context);
  return getMergedRules(collegeId ? { level: 'college', college_id: collegeId } : { level: 'school' });
}

module.exports = {
  MANAGE_RULE_ROLES,
  assertRuleConfigAccess,
  listEffectiveRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
  resolveRulesForAnalysis,
};
