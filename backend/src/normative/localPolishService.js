const crypto = require('crypto');
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
  const retryOf = typeof payload.retry_of === 'string' && payload.retry_of.trim() ? payload.retry_of.trim() : null;

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

function pushReplacement(changes, segments, originalText, newText, position, rule) {
  if (originalText === newText) {
    segments.push({ type: 'unchanged', text: originalText, position });
    return;
  }

  changes.push({ original_text: originalText, new_text: newText, position, rule });
  segments.push({
    type: 'replacement',
    original_text: originalText,
    new_text: newText,
    text: newText,
    position,
    rule,
  });
}

function appendUnchanged(segments, text, position) {
  if (!text) {
    return;
  }
  const previous = segments[segments.length - 1];
  if (previous?.type === 'unchanged') {
    previous.text += text;
    return;
  }
  segments.push({ type: 'unchanged', text, position });
}

function transformLocalText(text, level) {
  const changes = [];
  const segments = [];
  const pattern = /([ \t]{2,}|([！？!?。；;，,])\2+|([\p{Script=Han}]{2})\3)/gu;
  let polishedText = '';
  let lastIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const originalText = match[0];
    const position = match.index || 0;
    appendUnchanged(segments, text.slice(lastIndex, position), lastIndex);

    let newText = originalText;
    let rule = '基础校准：文本规范化';
    if (/^[ \t]{2,}$/u.test(originalText)) {
      newText = ' ';
      rule = '基础校准：归一化连续空白';
    } else if (match[2]) {
      newText = match[2];
      rule = '基础校准：修复重复标点';
    } else if (match[3]) {
      newText = match[3];
      rule = '基础校准：修复连续重复词';
    }

    polishedText += text.slice(lastIndex, position) + newText;
    pushReplacement(changes, segments, originalText, newText, position, rule);
    lastIndex = position + originalText.length;
  }

  polishedText += text.slice(lastIndex);
  appendUnchanged(segments, text.slice(lastIndex), lastIndex);

  if (level === 'standard' || level === 'enhanced') {
    const improved = polishedText.replace(/需要标准优化/g, '需要进一步优化').replace(/需要局部润色/g, '需要进行局部润色');
    if (improved !== polishedText) {
      changes.push({
        original_text: polishedText,
        new_text: improved,
        position: 0,
        rule: '标准优化：提升表达清晰度',
      });
      segments.length = 0;
      segments.push({ type: 'format', text: improved, position: 0, rule: '标准优化：提升表达清晰度' });
      polishedText = improved;
    }
  }

  if (level === 'enhanced') {
    let enhanced = polishedText.replace(/。/gu, '。\n').replace(/\n$/u, '');
    if (enhanced === polishedText) {
      enhanced = `经重构：${polishedText}`;
    }
    if (enhanced !== polishedText) {
      changes.push({
        original_text: polishedText,
        new_text: enhanced,
        position: 0,
        rule: 'AI 重构：按句重排段落节奏',
      });
      segments.length = 0;
      segments.push({ type: 'format', text: enhanced, position: 0, rule: 'AI 重构：按句重排段落节奏' });
      polishedText = enhanced;
    }
  }

  if (!changes.length) {
    const trimmed = text.trimEnd();
    if (trimmed !== text) {
      changes.push({ original_text: text, new_text: trimmed, position: 0, rule: '基础校准：去除尾部空白' });
      return {
        polished_text: trimmed,
        changes,
        diff_segments: [{ type: 'format', text: trimmed, position: 0, rule: '基础校准：去除尾部空白' }],
      };
    }
  }

  return { polished_text: polishedText, changes, diff_segments: segments };
}

async function createLocalPolishResult(user, payload = {}) {
  const normalized = normalizeLocalPolishPayload(payload);
  const generated = transformLocalText(normalized.text, normalized.level);
  const result = {
    id: crypto.randomUUID(),
    user_id: user.id,
    original_text: normalized.text,
    polished_text: generated.polished_text,
    level: normalized.level,
    rule_version: normalized.rule_version,
    changes: generated.changes,
    diff_segments: generated.diff_segments,
    source_result_id: normalized.retry_of,
    retry_of: normalized.retry_of,
    created_at: new Date().toISOString(),
  };

  return localPolishRepository.createLocalPolishResult(result);
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
