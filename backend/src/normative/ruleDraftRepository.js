const { all, run, withTransaction } = require('../database');

async function listRuleDrafts(scope = {}) {
  void scope;
  return all('SELECT * FROM normative_rule_drafts WHERE 1 = 0');
}

async function replaceRuleDrafts(scope, drafts, updatedBy) {
  void scope;
  void drafts;
  void updatedBy;
  return withTransaction(async () => ({ created: 0 }));
}

async function clearRuleDrafts(scope = {}) {
  void scope;
  return run('DELETE FROM normative_rule_drafts WHERE 1 = 0');
}

module.exports = {
  listRuleDrafts,
  replaceRuleDrafts,
  clearRuleDrafts,
};
