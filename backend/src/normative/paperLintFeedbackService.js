const { randomUUID } = require('crypto');
const db = require('../database/db_runtime');
const suggestionService = require('./paperLintRepairSuggestionService');

const FINDING_REASONS = new Set(['false_positive', 'location_inaccurate', 'description_unclear', 'other']);
const SUGGESTION_REASONS = new Set(['incorrect', 'not_directly_executable', 'insufficient_basis', 'unclear', 'other']);
const SYSTEM_AREAS = new Set(['detection_accuracy', 'ai_suggestion_quality', 'pdf_location', 'system_response_speed', 'system_stability', 'page_design', 'other']);

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function validateValue(value) {
  if (value !== 'positive' && value !== 'negative') throw problem(400, 'feedback_value 必须是 positive 或 negative');
}

function validateReason(value, allowed) {
  if (value == null || value === '') return null;
  if (!allowed.has(value)) throw problem(400, 'reason_code 不在允许范围内');
  return value;
}

function validateText(value) {
  if (value == null || value === '') return null;
  if (typeof value !== 'string' || value.length > 1000) throw problem(400, '补充说明不能超过 1000 个字符');
  return value.trim() || null;
}

function feedbackPayload(input, reasons) {
  const feedbackValue = input?.feedback_value;
  validateValue(feedbackValue);
  const reasonCode = feedbackValue === 'negative' ? validateReason(input.reason_code, reasons) : null;
  const reasonText = feedbackValue === 'negative' ? validateText(input.reason_text) : null;
  return { feedbackValue, reasonCode, reasonText };
}

function mapFeedback(row) {
  if (!row) return null;
  return {
    id: row.id,
    feedback_value: row.feedback_value,
    reason_code: row.reason_code,
    reason_text: row.reason_text,
    created_at: row.created_at,
    updated_at: row.updated_at,
    ...(row.suggestion_id ? { suggestion_id: row.suggestion_id, generation: row.generation } : {}),
  };
}

async function getFindingFeedback({ reportId, userId, ruleId, findingId }) {
  await suggestionService.getPaperLintReportFinding({ reportId, userId, ruleId, findingId });
  return mapFeedback(await db.get(
    `SELECT * FROM paper_lint_finding_feedback WHERE user_id=? AND report_id=? AND rule_id=? AND finding_id=?`,
    [userId, reportId, ruleId, findingId],
  ));
}

async function saveFindingFeedback({ reportId, userId, ruleId, findingId, input }) {
  await suggestionService.getPaperLintReportFinding({ reportId, userId, ruleId, findingId });
  const { feedbackValue, reasonCode, reasonText } = feedbackPayload(input, FINDING_REASONS);
  await db.withTransaction(async (tx) => {
    await tx.run(`INSERT INTO paper_lint_finding_feedback
      (id,user_id,report_id,rule_id,finding_id,feedback_value,reason_code,reason_text)
      VALUES (?,?,?,?,?,?,?,?)
      ON CONFLICT(user_id,report_id,rule_id,finding_id) DO UPDATE SET
      feedback_value=excluded.feedback_value, reason_code=excluded.reason_code,
      reason_text=excluded.reason_text, updated_at=CURRENT_TIMESTAMP`,
    [randomUUID(), userId, reportId, ruleId, findingId, feedbackValue, reasonCode, reasonText]);
  });
  return getFindingFeedback({ reportId, userId, ruleId, findingId });
}

async function deleteFindingFeedback({ reportId, userId, ruleId, findingId }) {
  await suggestionService.getPaperLintReportFinding({ reportId, userId, ruleId, findingId });
  await db.run(`DELETE FROM paper_lint_finding_feedback WHERE user_id=? AND report_id=? AND rule_id=? AND finding_id=?`, [userId, reportId, ruleId, findingId]);
}

async function getSuggestion({ reportId, userId, suggestionId }) {
  const row = await db.get(`SELECT * FROM paper_lint_repair_suggestions WHERE id=? AND report_id=? AND user_id=?`, [suggestionId, reportId, userId]);
  if (!row) throw problem(404, '未找到该版本的 AI 修复建议');
  await suggestionService.getPaperLintReportFinding({ reportId, userId, ruleId: row.rule_id, findingId: row.finding_id });
  return row;
}

async function getSuggestionFeedback(values) {
  const suggestion = await getSuggestion(values);
  return mapFeedback(await db.get(`SELECT * FROM paper_lint_suggestion_feedback WHERE user_id=? AND suggestion_id=?`, [values.userId, suggestion.id]));
}

async function saveSuggestionFeedback(values) {
  const suggestion = await getSuggestion(values);
  const { feedbackValue, reasonCode, reasonText } = feedbackPayload(values.input, SUGGESTION_REASONS);
  await db.withTransaction(async (tx) => {
    await tx.run(`INSERT INTO paper_lint_suggestion_feedback
      (id,user_id,report_id,rule_id,finding_id,suggestion_id,generation,feedback_value,reason_code,reason_text)
      VALUES (?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(user_id,suggestion_id) DO UPDATE SET
      feedback_value=excluded.feedback_value, reason_code=excluded.reason_code,
      reason_text=excluded.reason_text, updated_at=CURRENT_TIMESTAMP`,
    [randomUUID(), values.userId, values.reportId, suggestion.rule_id, suggestion.finding_id, suggestion.id, suggestion.generation, feedbackValue, reasonCode, reasonText]);
  });
  return getSuggestionFeedback(values);
}

async function deleteSuggestionFeedback(values) {
  const suggestion = await getSuggestion(values);
  await db.run(`DELETE FROM paper_lint_suggestion_feedback WHERE user_id=? AND suggestion_id=?`, [values.userId, suggestion.id]);
}

async function saveSystemFeedback({ userId, input }) {
  const score = Number(input?.satisfaction_score);
  if (!Number.isInteger(score) || score < 1 || score > 5) throw problem(400, '满意度必须是 1 至 5 分');
  const areas = Array.isArray(input?.improvement_areas) ? [...new Set(input.improvement_areas)] : [];
  if (areas.some((area) => !SYSTEM_AREAS.has(area))) throw problem(400, '改进方向不在允许范围内');
  const comment = validateText(input?.comment);
  const requestId = input?.request_id == null ? null : String(input.request_id).trim().slice(0, 128) || null;
  const existing = requestId ? await db.get('SELECT id FROM system_feedback WHERE user_id=? AND request_id=?', [userId, requestId]) : null;
  if (existing) return { id: existing.id, duplicate: true };
  const id = randomUUID();
  await db.run(`INSERT INTO system_feedback (id,user_id,satisfaction_score,improvement_areas_json,comment,request_id) VALUES (?,?,?,?,?,?)`, [id, userId, score, JSON.stringify(areas), comment, requestId]);
  return { id, duplicate: false };
}

module.exports = { getFindingFeedback, saveFindingFeedback, deleteFindingFeedback, getSuggestionFeedback, saveSuggestionFeedback, deleteSuggestionFeedback, saveSystemFeedback };
