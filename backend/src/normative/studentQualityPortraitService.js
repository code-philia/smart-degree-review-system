const { buildLedgerAccessScope } = require('./ledgerRecordsService');
const ledgerRecordsRepository = require('./ledgerRecordsRepository');
const studentQualityPortraitRepository = require('./studentQualityPortraitRepository');

const ALLOWED_STUDENT_QUALITY_PORTRAIT_ROLES = ['STUDENT', 'SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'];

function createStudentQualityPortraitError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function buildStudentPortraitAccessScope(user, requestedStudentId) {
  if (!user) {
    throw createStudentQualityPortraitError(401, '请先登录后查看单学生质量画像');
  }
  if (!ALLOWED_STUDENT_QUALITY_PORTRAIT_ROLES.includes(user.role)) {
    throw createStudentQualityPortraitError(403, '当前角色无权查看单学生质量画像');
  }
  if (user.role === 'STUDENT') {
    const ownStudentId = user.id || user.username;
    if (!requestedStudentId || requestedStudentId !== ownStudentId) {
      throw createStudentQualityPortraitError(403, '学生仅可查看本人质量画像');
    }
    return { role: 'STUDENT', student_id: ownStudentId };
  }
  return buildLedgerAccessScope(user);
}

function toStudentQualityPortraitFilters(query = {}) {
  return ledgerRecordsRepository.normalizeLedgerFilters({
    from: query.from,
    to: query.to,
    latest_only: true,
  });
}

async function getStudentQualityPortraitForUser(user, studentId, query = {}) {
  const normalizedStudentId = String(studentId || '').trim();
  if (!normalizedStudentId) {
    throw createStudentQualityPortraitError(400, '学生画像 ID 不能为空');
  }
  const scope = buildStudentPortraitAccessScope(user, normalizedStudentId);
  return studentQualityPortraitRepository.getStudentQualityPortrait(
    scope,
    normalizedStudentId,
    toStudentQualityPortraitFilters(query),
  );
}

module.exports = {
  ALLOWED_STUDENT_QUALITY_PORTRAIT_ROLES,
  buildStudentPortraitAccessScope,
  getStudentQualityPortraitForUser,
  toStudentQualityPortraitFilters,
};
