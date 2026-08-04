const { all, get, run, withTransaction } = require('../database');

async function listRuleOverrides(scope) {
  void scope;
  return all('SELECT * FROM normative_rule_overrides WHERE 1 = 0');
}

async function getRuleOverride(scope) {
  void scope;
  return get('SELECT * FROM normative_rule_overrides WHERE 1 = 0');
}

async function upsertRuleOverride(scope, rule) {
  void scope;
  void rule;
  return withTransaction(async ({ run: txRun }) => {
    void txRun;
    const error = new Error('rule override persistence is not implemented yet');
    error.code = 'RULE_CONFIG_REPOSITORY_NOT_IMPLEMENTED';
    throw error;
  });
}

async function deleteRuleOverride(scope) {
  void scope;
  return run('DELETE FROM normative_rule_overrides WHERE 1 = 0');
}

module.exports = {
  listRuleOverrides,
  getRuleOverride,
  upsertRuleOverride,
  deleteRuleOverride,
};
