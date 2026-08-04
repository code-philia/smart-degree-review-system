const crypto = require('crypto');
const { all, get, run, withTransaction } = require('../database');

function normalizeScope(scope = {}) {
  const scopeLevel = scope.scope_level || scope.level;
  const collegeId = scope.college_id || scope.collegeId || null;
  return {
    scope_level: scopeLevel,
    college_id: scopeLevel === 'college' ? collegeId : null,
    rule_id: scope.rule_id || null,
  };
}

function normalizeRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    scope_level: row.scope_level,
    college_id: row.college_id,
    rule_id: row.rule_id,
    title: row.title,
    category: row.category,
    severity: row.severity,
    enabled: Boolean(row.enabled),
    match_params: JSON.parse(row.match_params_json || '{}'),
    match_params_json: row.match_params_json,
    prompt: row.prompt,
    updated_by: row.updated_by,
    updated_at: row.updated_at,
  };
}

async function listRuleOverrides(scope = {}) {
  const normalizedScope = normalizeScope(scope);
  if (normalizedScope.scope_level === 'college') {
    const rows = await all(
      `SELECT * FROM normative_rule_overrides
        WHERE scope_level = 'college' AND college_id = ?
        ORDER BY rule_id`,
      [normalizedScope.college_id],
    );
    return rows.map(normalizeRow);
  }

  const rows = await all(
    `SELECT * FROM normative_rule_overrides
      WHERE scope_level = 'school'
      ORDER BY rule_id, updated_at DESC`,
  );
  const byRuleId = new Map();
  rows.forEach((row) => {
    if (!byRuleId.has(row.rule_id)) {
      byRuleId.set(row.rule_id, normalizeRow(row));
    }
  });
  return Array.from(byRuleId.values());
}

async function getRuleOverride(scope = {}) {
  const normalizedScope = normalizeScope(scope);
  const row = normalizedScope.scope_level === 'college'
    ? await get(
      `SELECT * FROM normative_rule_overrides
        WHERE scope_level = 'college' AND college_id = ? AND rule_id = ?
        ORDER BY updated_at DESC
        LIMIT 1`,
      [normalizedScope.college_id, normalizedScope.rule_id],
    )
    : await get(
      `SELECT * FROM normative_rule_overrides
        WHERE scope_level = 'school' AND rule_id = ?
        ORDER BY updated_at DESC
        LIMIT 1`,
      [normalizedScope.rule_id],
    );
  return normalizeRow(row);
}

async function upsertRuleOverride(scope, rule) {
  const normalizedScope = normalizeScope(scope);
  const id = `${normalizedScope.scope_level}:${normalizedScope.college_id || 'school'}:${rule.rule_id}:${crypto.randomUUID()}`;
  const matchParamsJson = JSON.stringify(rule.match_params || {});

  return withTransaction(async ({ run: txRun }) => {
    if (normalizedScope.scope_level === 'school') {
      await txRun(
        `DELETE FROM normative_rule_overrides
          WHERE scope_level = 'school' AND rule_id = ?`,
        [rule.rule_id],
      );
    } else {
      await txRun(
        `DELETE FROM normative_rule_overrides
          WHERE scope_level = 'college' AND college_id = ? AND rule_id = ?`,
        [normalizedScope.college_id, rule.rule_id],
      );
    }

    await txRun(
      `INSERT INTO normative_rule_overrides (
        id, scope_level, college_id, rule_id, title, category, severity, enabled, match_params_json, prompt, updated_by, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
      [
        id,
        normalizedScope.scope_level,
        normalizedScope.college_id,
        rule.rule_id,
        rule.title,
        rule.category,
        rule.severity,
        rule.enabled ? 1 : 0,
        matchParamsJson,
        rule.prompt,
        rule.updated_by,
      ],
    );

    return getRuleOverride({ ...normalizedScope, rule_id: rule.rule_id });
  });
}

async function deleteRuleOverride(scope) {
  const normalizedScope = normalizeScope(scope);
  if (normalizedScope.scope_level !== 'college') {
    return { changes: 0 };
  }
  return run(
    `DELETE FROM normative_rule_overrides
      WHERE scope_level = 'college' AND college_id = ? AND rule_id = ?`,
    [normalizedScope.college_id, normalizedScope.rule_id],
  );
}

module.exports = {
  listRuleOverrides,
  getRuleOverride,
  upsertRuleOverride,
  deleteRuleOverride,
};
