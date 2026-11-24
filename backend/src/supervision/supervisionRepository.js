const db = require('../database');
const reports = require('../normative/paperLintReportRepository');
const { feedbackRowsSql, feedbackReasonLabels, feedbackAreaLabels, feedbackTypeLabels } = require('../normative/feedbackArchive');
const { getRuleDefinition } = require('../../rules/registry');

function invalid() { const error = new Error('筛选条件或页码无效'); error.status = 400; throw error; }
function text(value, limit = 200) {
  if (value === undefined) return '';
  if (typeof value !== 'string' || value.length > limit) invalid();
  return value.trim();
}
function paging(query) {
  const number = (value, fallback, max) => {
    if (value === undefined) return fallback;
    if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) invalid();
    const n = Number(value); if (!Number.isSafeInteger(n) || n > max) invalid(); return n;
  };
  const page = number(query.page, 1, 1_000_000), pageSize = number(query.page_size, 20, 50);
  return { page, page_size: pageSize, offset: (page - 1) * pageSize };
}
const owner = row => ({ id: row.user_id, username: row.username || row.user_id, display_name: row.display_name || null });
const negative = "(type='system' AND satisfaction_score<=2) OR feedback_value='negative'";
const reportTables = { paper_lint: 'paper_lint_reports', normative: 'normative_detection_tasks', duplication: 'duplication_detection_reports', example: 'example_rule_reports' };
const reportLabels = { paper_lint: '论文规范检测', normative: '早期规范检测', duplication: '查重检测', example: '示例规则检测' };
const reportIndex = Object.entries(reportTables).map(([type, table]) => `SELECT id,user_id,source_filename,created_at,'${type}' AS report_type FROM ${table}`).join(' UNION ALL ');
const ownerJoin = ' LEFT JOIN auth_users u ON u.id=r.user_id OR (u.username=r.user_id AND NOT EXISTS (SELECT 1 FROM auth_users exact WHERE exact.id=r.user_id))';
function reportType(value) { const type = text(value, 20) || 'paper_lint'; if (!Object.hasOwn(reportTables, type)) invalid(); return type; }
function savedJson(value) { try { return JSON.parse(value); } catch { return null; } }
function searchColumn(query, columns, fallback) {
  const field = text(query.search_field, 30) || fallback;
  if (!Object.hasOwn(columns, field)) invalid();
  return columns[field];
}

async function summary() {
  const users = await db.get('SELECT count(*) AS n FROM auth_users');
  const reportCount = await db.get(`SELECT count(*) AS n FROM (${reportIndex})`);
  const feedback = await db.get(`SELECT count(*) AS n,coalesce(sum(CASE WHEN ${negative} THEN 1 ELSE 0 END),0) AS negative FROM (${feedbackRowsSql})`);
  return { users: users.n, reports: reportCount.n, feedback: feedback.n, negative_feedback: feedback.negative };
}

async function listReports(query) {
  const page = paging(query), q = text(query.q), userId = text(query.user_id, 160);
  const where = [], values = [];
  const column = searchColumn(query, { filename: 'r.source_filename', display_name: 'u.display_name', username: 'u.username', report_id: 'r.id' }, 'filename');
  if (query.type && query.type !== 'all') { where.push('r.report_type=?'); values.push(reportType(query.type)); }
  if (q) { where.push(`instr(lower(coalesce(${column},'')),lower(?))>0`); values.push(q); }
  if (userId) { where.push('r.user_id=?'); values.push(userId); }
  const from = ` FROM (${reportIndex}) r` + ownerJoin + (where.length ? ' WHERE ' + where.join(' AND ') : '');
  const total = (await db.get('SELECT count(*) AS n' + from, values)).n;
  const rows = await db.all('SELECT r.*,u.username,u.display_name' + from + ' ORDER BY r.created_at DESC,r.report_type,r.id DESC LIMIT ? OFFSET ?', [...values, page.page_size, page.offset]);
  const items = await Promise.all(rows.map(async row => {
    const base = { report_type: row.report_type, type_label: reportLabels[row.report_type], owner: owner(row) };
    if (row.report_type !== 'paper_lint') return { ...base, id: row.id, source_filename: row.source_filename || '粘贴文本检测', created_at: row.created_at, summary: null };
    try { const source = await db.get('SELECT * FROM paper_lint_reports WHERE id=?', [row.id]); return { ...await reports.toPaperLintReport(source, { includeResult: false }), ...base }; }
    catch { return { id: row.id, source_filename: row.source_filename, created_at: row.created_at, owner: owner(row), summary: null, unavailable: true }; }
  }));
  return { items, total, page: page.page, page_size: page.page_size };
}

async function reportOwner(id) {
  return db.get('SELECT r.id,r.user_id,u.username,u.display_name FROM paper_lint_reports r LEFT JOIN auth_users u ON u.id=r.user_id WHERE r.id=?', [id]);
}
async function reportDetail(id, requestedType) {
  const type = reportType(requestedType);
  if (type !== 'paper_lint') {
    const row = await db.get(`SELECT r.*,u.username,u.display_name FROM ${reportTables[type]} r` + ownerJoin + ' WHERE r.id=?', [id]);
    if (!row) return null;
    const saved = type === 'normative' ? { issues: savedJson(row.issues_json), severity_counts: savedJson(row.severity_counts_json) }
      : savedJson(type === 'duplication' ? row.report_json : row.result_json);
    return { owner: owner(row), legacy: { id, report_type: type, type_label: reportLabels[type], source_filename: row.source_filename || '粘贴文本检测', created_at: row.created_at,
      original_text: row.original_text || '', saved_result: saved, has_pdf: type === 'example' } };
  }
  const row = await reportOwner(id); if (!row) return null;
  const report = await reports.findPaperLintReportByIdForUser(id, row.user_id);
  return { report, owner: owner(row) };
}
async function reportPdf(id, requestedType) {
  const type = reportType(requestedType);
  if (type !== 'paper_lint') {
    if (type !== 'example') return null;
    const row = await db.get('SELECT source_pdf_path,source_filename FROM example_rule_reports WHERE id=?', [id]);
    if (!row) return null;
    try { await require('fs').promises.access(row.source_pdf_path); return { path: row.source_pdf_path, source_filename: row.source_filename }; }
    catch { return { path: null, source_filename: row.source_filename }; }
  }
  const row = await reportOwner(id); if (!row) return null;
  return reports.getPaperLintReportPdfFile(id, row.user_id);
}

async function listFeedback(query) {
  const page = paging(query), q = text(query.q), type = text(query.type, 20), value = text(query.value, 20);
  if (type && !['all','system','finding','suggestion'].includes(type)) invalid();
  if (value && !['all','positive','negative'].includes(value)) invalid();
  const where = [], values = [];
  const column = searchColumn(query, { content: "coalesce(comment,'')||' '||coalesce(reason_text,'')", filename: 'source_filename', display_name: 'display_name', username: 'username', rule_id: 'rule_id' }, 'content');
  if (type && type !== 'all') { where.push('type=?'); values.push(type); }
  if (value && value !== 'all') {
    where.push(value === 'negative' ? '(' + negative + ')' : "((type='system' AND satisfaction_score>=4) OR feedback_value='positive')");
  }
  if (q) { where.push(`instr(lower(coalesce(${column},'')),lower(?))>0`); values.push(q); }
  const from = ' FROM (' + feedbackRowsSql + ') feedback' + (where.length ? ' WHERE ' + where.join(' AND ') : '');
  const total = (await db.get('SELECT count(*) AS n' + from, values)).n;
  const rows = await db.all('SELECT *' + from + ' ORDER BY created_at DESC,type,id DESC LIMIT ? OFFSET ?', [...values, page.page_size, page.offset]);
  const reportIds = [...new Set(rows.map(r => r.report_id).filter(Boolean))];
  const context = reportIds.length ? await db.all('SELECT id,result_json FROM paper_lint_reports WHERE id IN (' + reportIds.map(() => '?').join(',') + ')', reportIds) : [];
  const byId = new Map(context.map(row => { try { return [row.id, JSON.parse(row.result_json)]; } catch { return [row.id, null]; } }));
  const suggestionIds = [...new Set(rows.map(row => row.suggestion_id).filter(Boolean))];
  const savedSuggestions = suggestionIds.length ? await db.all('SELECT id,generation,status,response_json FROM paper_lint_repair_suggestions WHERE id IN (' + suggestionIds.map(() => '?').join(',') + ')', suggestionIds) : [];
  const suggestions = new Map(savedSuggestions.map(row => {
    let actions = []; try { const saved = JSON.parse(row.response_json); actions = Array.isArray(saved.actions) ? saved.actions : []; } catch { /* legacy invalid response */ }
    return [row.id, { id: row.id, generation: row.generation, status: row.status, actions: actions.filter(action => action && typeof action === 'object').map(action => ({
      instruction: typeof action.instruction === 'string' ? action.instruction : '',
      original_text: typeof action.original_text === 'string' ? action.original_text : '',
      replacement: typeof action.replacement === 'string' ? action.replacement : '',
    })) }];
  }));
  const items = rows.map(row => {
    let areas = []; try { areas = JSON.parse(row.improvement_areas_json || '[]'); } catch { /* malformed legacy value */ }
    const run = byId.get(row.report_id)?.rule_runs?.find(r => r.rule_id === row.rule_id);
    const finding = run?.findings?.find(f => f.finding_id === row.finding_id);
    const { improvement_areas_json, ...record } = row;
    return { ...record, type_label: feedbackTypeLabels[row.type], reason_label: feedbackReasonLabels[row.reason_code] || row.reason_code || '',
      feedback_label: row.type === 'system' ? `${row.satisfaction_score} 分` : row.feedback_value === 'negative' ? '点踩' : '点赞',
      improvement_labels: Array.isArray(areas) ? areas.map(area => feedbackAreaLabels[area] || area) : [],
      rule_title: getRuleDefinition(row.rule_id)?.title || run?.title || row.rule_id || null,
      finding_text: finding?.message || run?.message || null,
      saved_suggestion: suggestions.get(row.suggestion_id) || null };
  });
  return { items, total, page: page.page, page_size: page.page_size };
}

module.exports = { summary, listReports, listFeedback, reportDetail, reportPdf };
