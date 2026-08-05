const ledgerRecordsRepository = require('./ledgerRecordsRepository');

const ALLOWED_LEDGER_RECORD_ROLES = ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'];

function createLedgerRecordsError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function buildLedgerAccessScope(user) {
  if (!user) {
    throw createLedgerRecordsError(401, '请先登录后查看检测台账');
  }
  if (!ALLOWED_LEDGER_RECORD_ROLES.includes(user.role)) {
    throw createLedgerRecordsError(403, '当前角色无权查看检测台账');
  }
  if (user.role === 'SUPERVISOR') {
    return { role: user.role, supervisor_id: user.id || user.username };
  }
  if (user.role === 'COLLEGE_ADMIN') {
    return { role: user.role, college_id: user.college_id };
  }
  return { role: user.role };
}

function toLedgerFilters(query = {}) {
  return ledgerRecordsRepository.normalizeLedgerFilters({
    student: query.student,
    detection_type: query.detection_type,
    from: query.from,
    to: query.to,
    latest_only: query.latest_only,
  });
}

async function listLedgerRecordsForUser(user, query = {}) {
  const scope = buildLedgerAccessScope(user);
  return ledgerRecordsRepository.listLedgerRecords(scope, toLedgerFilters(query));
}

async function getLedgerRecordForUser(user, recordId) {
  const scope = buildLedgerAccessScope(user);
  if (!recordId) {
    throw createLedgerRecordsError(400, '台账记录编号不能为空');
  }
  const record = await ledgerRecordsRepository.findLedgerRecordById(scope, recordId);
  if (!record) {
    throw createLedgerRecordsError(403, '无权访问该台账记录');
  }
  return record;
}

function buildLedgerCsv(records) {
  const header = ['记录ID', '学院', '学号', '姓名', '导师', '学生类别', '论文题目', '检测类型', '检测模板', '核心结果', '详情链接', '检测时间'];
  const rows = records.map((record) => [
    record.id,
    record.college_name,
    record.student_number,
    record.student_name,
    record.supervisor_name,
    record.student_category,
    record.thesis_title,
    record.detection_type,
    record.template_name,
    record.core_result,
    record.detail_url,
    record.created_at,
  ]);
  const escapeCell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  return [header, ...rows].map((row) => row.map(escapeCell).join(',')).join('\n');
}

async function exportLedgerRecordsCsvForUser(user, query = {}) {
  const records = await listLedgerRecordsForUser(user, query);
  return buildLedgerCsv(records);
}

async function getLedgerFilteredStatsForUser(user, query = {}) {
  const scope = buildLedgerAccessScope(user);
  return ledgerRecordsRepository.summarizeLedgerRecords(scope, toLedgerFilters(query));
}

module.exports = {
  ALLOWED_LEDGER_RECORD_ROLES,
  buildLedgerAccessScope,
  buildLedgerCsv,
  exportLedgerRecordsCsvForUser,
  getLedgerFilteredStatsForUser,
  getLedgerRecordForUser,
  listLedgerRecordsForUser,
  toLedgerFilters,
};
