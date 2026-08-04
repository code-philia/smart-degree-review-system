const crypto = require('crypto');
const { resolveRulesForAnalysis } = require('./ruleConfigService');
const wholePolishRepository = require('./wholePolishRepository');

const ALLOWED_WHOLE_POLISH_ROLES = Object.freeze(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
const MAX_WHOLE_POLISH_TEXT_BYTES = '5mb';
const WHOLE_POLISH_LEVELS = Object.freeze(['basic', 'standard', 'enhanced']);

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function normalizePayload(payload = {}) {
  const text = typeof payload.text === 'string' ? payload.text : '';
  const level = typeof payload.level === 'string' ? payload.level : 'basic';

  if (!text.trim()) {
    throw createHttpError(400, '润色文本不能为空');
  }
  if (!WHOLE_POLISH_LEVELS.includes(level)) {
    throw createHttpError(400, '润色档位无效');
  }

  return {
    text,
    level,
    source_type: payload.source_type === 'file' ? 'file' : 'paste',
    source_filename: typeof payload.source_filename === 'string' ? payload.source_filename : null,
  };
}

function buildDownloadText(result) {
  return result.polished_text;
}

async function createWholePolishResult(user, payload = {}) {
  const normalized = normalizePayload(payload);
  const effectiveRules = await resolveRulesForAnalysis({ college_id: user?.collegeId });

  const result = {
    id: crypto.randomUUID(),
    user_id: user.id,
    source_type: normalized.source_type,
    source_filename: normalized.source_filename,
    original_text: normalized.text,
    polished_text: normalized.text,
    level: normalized.level,
    changes: [],
    rule_snapshot: effectiveRules,
    created_at: new Date().toISOString(),
  };

  return wholePolishRepository.createWholePolishResult(result);
}

async function getWholePolishResultForUser(user, resultId) {
  const result = await wholePolishRepository.getWholePolishResultForUser(user.id, resultId);
  if (!result) {
    throw createHttpError(404, '未找到润色结果');
  }
  return result;
}

module.exports = {
  ALLOWED_WHOLE_POLISH_ROLES,
  MAX_WHOLE_POLISH_TEXT_BYTES,
  WHOLE_POLISH_LEVELS,
  buildDownloadText,
  createWholePolishResult,
  getWholePolishResultForUser,
};
