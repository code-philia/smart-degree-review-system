const localPolishRepository = require('./localPolishRepository');

const ALLOWED_LOCAL_POLISH_ROLES = Object.freeze(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
const LOCAL_POLISH_LEVELS = Object.freeze(['basic', 'standard', 'enhanced']);
const LOCAL_POLISH_RULE_VERSION = 'local-polish-v1';
const MAX_LOCAL_POLISH_TEXT_BYTES = '5mb';

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function normalizeLocalPolishPayload(payload = {}) {
  const text = typeof payload.text === 'string' ? payload.text : '';
  const level = typeof payload.level === 'string' ? payload.level : 'standard';
  const retryOf = typeof payload.retry_of === 'string' ? payload.retry_of : null;

  if (!text.trim()) {
    throw createHttpError(400, '局部润色文本不能为空');
  }
  if (!LOCAL_POLISH_LEVELS.includes(level)) {
    throw createHttpError(400, '局部润色档位无效');
  }

  return {
    text,
    level,
    retry_of: retryOf,
    rule_version: LOCAL_POLISH_RULE_VERSION,
  };
}

async function createLocalPolishResult(_user, payload = {}) {
  normalizeLocalPolishPayload(payload);
  const error = new Error('局部润色服务尚未实现');
  error.code = 'LOCAL_POLISH_SERVICE_NOT_IMPLEMENTED';
  throw error;
}

async function getLocalPolishResultForUser(user, resultId) {
  const result = await localPolishRepository.getLocalPolishResultForUser(user.id, resultId);
  if (!result) {
    throw createHttpError(404, '未找到局部润色结果');
  }
  return result;
}

module.exports = {
  ALLOWED_LOCAL_POLISH_ROLES,
  LOCAL_POLISH_LEVELS,
  LOCAL_POLISH_RULE_VERSION,
  MAX_LOCAL_POLISH_TEXT_BYTES,
  createLocalPolishResult,
  getLocalPolishResultForUser,
  normalizeLocalPolishPayload,
};
