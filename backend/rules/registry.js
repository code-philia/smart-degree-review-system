const registry = require('./registry.json');

const definitions = Object.freeze(registry.rules.map((rule) => Object.freeze({ ...rule })));
const byId = new Map(definitions.map((rule) => [rule.rule_id, rule]));

function listRuleDefinitions({ family, enabledInMvp, repairSurface } = {}) {
  return definitions.filter((rule) =>
    (family === undefined || rule.family === family) &&
    (enabledInMvp === undefined || rule.enabled_in_mvp === enabledInMvp) &&
    (repairSurface === undefined || rule.repair_surfaces.includes(repairSurface))
  );
}

function getRuleDefinition(ruleId) {
  return byId.get(ruleId) || null;
}

function requireRuleDefinition(ruleId) {
  const rule = getRuleDefinition(ruleId);
  if (!rule) {
    const error = new Error(`未知规则：${ruleId}`);
    error.status = 400;
    throw error;
  }
  return rule;
}

function getEnabledMvpRuleIds() {
  return listRuleDefinitions({ enabledInMvp: true }).map((rule) => rule.rule_id);
}

function supportsRepairSurface(ruleId, surface) {
  return Boolean(getRuleDefinition(ruleId)?.repair_surfaces?.includes(surface));
}

module.exports = {
  schemaVersion: registry.schema_version,
  listRuleDefinitions,
  getRuleDefinition,
  requireRuleDefinition,
  getEnabledMvpRuleIds,
  supportsRepairSurface,
};
