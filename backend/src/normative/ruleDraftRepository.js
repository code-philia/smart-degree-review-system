const crypto = require('crypto');
const { all, run, withTransaction } = require('../database');

function scopeWhere(scope = {}) {
  if (scope.level === 'college') {
    return {
      clause: 'scope_level = ? AND college_id = ?',
      params: ['college', scope.college_id],
      level: 'college',
      collegeId: scope.college_id,
    };
  }

  return {
    clause: 'scope_level = ? AND college_id IS NULL',
    params: ['school'],
    level: 'school',
    collegeId: null,
  };
}

function mapDraftRow(row) {
  return {
    id: row.id,
    import_batch_id: row.import_batch_id,
    rule_id: row.rule_id,
    title: row.title,
    category: row.category,
    severity: row.severity,
    enabled: Boolean(row.enabled),
    message: row.message,
    params: row.params_json ? JSON.parse(row.params_json) : {},
    scope: { level: row.scope_level, college_id: row.college_id || null },
    updated_by: row.updated_by,
    created_at: row.created_at,
  };
}

async function listRuleDrafts(scope = {}) {
  const resolved = scopeWhere(scope);
  const rows = await all(
    `SELECT * FROM normative_rule_drafts
      WHERE ${resolved.clause}
      ORDER BY created_at ASC, rule_id ASC`,
    resolved.params,
  );
  return rows.map(mapDraftRow);
}

async function replaceRuleDrafts(scope, drafts, updatedBy) {
  const resolved = scopeWhere(scope);
  const importBatchId = crypto.randomUUID();

  return withTransaction(async (tx) => {
    await tx.run(`DELETE FROM normative_rule_drafts WHERE ${resolved.clause}`, resolved.params);

    const persisted = [];
    for (const draft of drafts) {
      const id = `${resolved.level}:${resolved.collegeId || 'school'}:${draft.rule_id}`;
      await tx.run(
        `INSERT INTO normative_rule_drafts (
          id, import_batch_id, scope_level, college_id, rule_id, title, category, severity, enabled, message, params_json, updated_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          id,
          importBatchId,
          resolved.level,
          resolved.collegeId,
          draft.rule_id,
          draft.title,
          draft.category,
          draft.severity,
          draft.enabled ? 1 : 0,
          draft.message,
          JSON.stringify(draft.params || {}),
          updatedBy,
        ],
      );
      persisted.push({ ...draft, import_batch_id: importBatchId });
    }

    return {
      draft_batch_id: importBatchId,
      created: persisted.length,
      drafts: persisted,
    };
  });
}

async function clearRuleDrafts(scope = {}) {
  const resolved = scopeWhere(scope);
  return run(`DELETE FROM normative_rule_drafts WHERE ${resolved.clause}`, resolved.params);
}

module.exports = {
  listRuleDrafts,
  replaceRuleDrafts,
  clearRuleDrafts,
};
