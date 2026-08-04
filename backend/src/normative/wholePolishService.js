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

function pushChange(changes, originalText, newText, position, rule, reason) {
  const change = { original_text: originalText, new_text: newText, position, rule };
  if (reason) {
    change.reason = reason;
  }
  changes.push(change);
}

function replaceWithChangeTracking(text, pattern, replacement, changes, rule, getReason) {
  let output = '';
  let lastIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const originalText = match[0];
    const position = match.index || 0;
    const newText = typeof replacement === 'function' ? replacement(match) : replacement;

    if (originalText === newText) {
      continue;
    }

    output += text.slice(lastIndex, position);
    output += newText;
    pushChange(changes, originalText, newText, position, rule, getReason ? getReason(match) : undefined);
    lastIndex = position + originalText.length;
  }

  output += text.slice(lastIndex);
  return output;
}

function applyBasicPolish(text, changes) {
  let polished = text;
  polished = replaceWithChangeTracking(polished, /[ \t]+$/gmu, '', changes, '基础校准：去除行尾空格');
  polished = replaceWithChangeTracking(polished, /[ \t]{2,}/gu, ' ', changes, '基础校准：归一化连续空白');
  polished = replaceWithChangeTracking(
    polished,
    /([！？!?。；;，,])\1+/gu,
    (match) => match[1],
    changes,
    '基础校准：修复重复标点',
  );
  polished = replaceWithChangeTracking(
    polished,
    /([\p{Script=Han}]{2})\1/gu,
    (match) => match[1],
    changes,
    '基础校准：修复连续重复词',
  );
  return polished;
}

function getPhraseMappings(effectiveRules) {
  return effectiveRules
    .filter((rule) => rule.enabled !== false)
    .flatMap((rule) => {
      const replacements = rule.match_params?.replacements || rule.match_params?.phrase_mappings || [];
      return Array.isArray(replacements) ? replacements : [];
    })
    .map((mapping) => ({
      original: String(mapping.original || mapping.original_text || mapping.from || ''),
      replacement: String(mapping.replacement || mapping.new_text || mapping.to || ''),
    }))
    .filter((mapping) => mapping.original && mapping.original !== mapping.replacement);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function applyPhraseMappings(text, effectiveRules, changes) {
  let polished = text;
  for (const mapping of getPhraseMappings(effectiveRules)) {
    polished = replaceWithChangeTracking(
      polished,
      new RegExp(escapeRegExp(mapping.original), 'gu'),
      mapping.replacement,
      changes,
      '标准优化：管理员短语映射',
    );
  }
  return polished;
}

function applyEnhancedSplits(text, changes) {
  let polished = text;
  let searchStart = 0;

  while (searchStart < polished.length) {
    const sentenceEndMatch = /[。.!?！？]/u.exec(polished.slice(searchStart));
    const sentenceEnd = sentenceEndMatch ? searchStart + sentenceEndMatch.index + sentenceEndMatch[0].length : polished.length;
    const sentence = polished.slice(searchStart, sentenceEnd);

    if (sentence.length > 120 || Buffer.byteLength(sentence, 'utf8') > 120) {
      const separatorIndex = sentence.search(/[，,；;]/u);
      if (separatorIndex >= 0 && sentence[separatorIndex + 1] !== '\n') {
        const position = searchStart + separatorIndex;
        const originalText = polished[position];
        const newText = `${originalText}\n`;
        polished = `${polished.slice(0, position)}${newText}${polished.slice(position + 1)}`;
        pushChange(
          changes,
          originalText,
          newText,
          position,
          '增强优化：长句合法分隔位置拆分',
          '句子超过 120 字符，按首个合法分隔符 separator 拆分',
        );
        searchStart = position + newText.length;
        continue;
      }
    }

    searchStart = sentenceEnd + 1;
  }

  return polished;
}

async function createWholePolishResult(user, payload = {}) {
  const normalized = normalizePayload(payload);
  const effectiveRules = await resolveRulesForAnalysis({ college_id: user?.collegeId || user?.college_id });
  const changes = [];
  let polishedText = applyBasicPolish(normalized.text, changes);

  if (normalized.level === 'standard' || normalized.level === 'enhanced') {
    polishedText = applyPhraseMappings(polishedText, effectiveRules, changes);
  }
  if (normalized.level === 'enhanced') {
    polishedText = applyEnhancedSplits(polishedText, changes);
  }

  const result = {
    id: crypto.randomUUID(),
    user_id: user.id,
    source_type: normalized.source_type,
    source_filename: normalized.source_filename,
    original_text: normalized.text,
    polished_text: polishedText,
    level: normalized.level,
    changes,
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
