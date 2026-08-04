const polishHistoryRepository = require('./polishHistoryRepository');

const ALLOWED_POLISH_HISTORY_ROLES = Object.freeze(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
const POLISH_HISTORY_TYPES = Object.freeze(['whole', 'local']);

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function ensureCanAccessPolishHistory(user) {
  if (!user?.id) {
    throw createHttpError(401, '请先登录后查看润色记录');
  }
  if (!ALLOWED_POLISH_HISTORY_ROLES.includes(user.role)) {
    throw createHttpError(403, '当前角色无权查看润色记录');
  }
  return user.id;
}

async function listPolishHistoryForUser(user) {
  const ownerId = ensureCanAccessPolishHistory(user);
  return polishHistoryRepository.listPolishHistoryByUser(ownerId);
}

async function getPolishHistoryRecordForUser(user, polishType, resultId) {
  const ownerId = ensureCanAccessPolishHistory(user);
  if (!POLISH_HISTORY_TYPES.includes(polishType)) {
    throw createHttpError(400, '润色记录类型无效');
  }
  if (!resultId) {
    throw createHttpError(400, '润色记录编号不能为空');
  }

  const record = await polishHistoryRepository.findPolishHistoryRecordForUser(polishType, resultId, ownerId);
  if (!record) {
    throw createHttpError(404, '润色记录不存在或无权访问');
  }
  return record;
}

function buildPolishResultText(record) {
  return record.polished_text || '';
}

module.exports = {
  ALLOWED_POLISH_HISTORY_ROLES,
  POLISH_HISTORY_TYPES,
  buildPolishResultText,
  ensureCanAccessPolishHistory,
  getPolishHistoryRecordForUser,
  listPolishHistoryForUser,
};
