const { listCorpusSamples } = require('./duplicationCorpusRepository');

const MAX_DUPLICATION_DETECTION_TEXT_BYTES = 5 * 1024 * 1024;
const DEFAULT_DUPLICATION_MATCH_THRESHOLD = 0.65;
const ALLOWED_DUPLICATION_DETECTION_ROLES = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];

function serviceError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function ensureAuthorizedUser(user) {
  if (!user) {
    throw serviceError(401, '请先登录');
  }
  if (!ALLOWED_DUPLICATION_DETECTION_ROLES.includes(user.role)) {
    throw serviceError(403, '当前角色无权发起相似度检测');
  }
}

function validateDetectionPayload(payload = {}) {
  const text = typeof payload.text === 'string' ? payload.text.trim() : '';
  if (!text) {
    throw serviceError(400, '待检文本不能为空');
  }
  if (Buffer.byteLength(text, 'utf8') > MAX_DUPLICATION_DETECTION_TEXT_BYTES) {
    throw serviceError(413, '待检文本不能超过 5 MB');
  }

  return {
    text,
    source_type: payload.source_type === 'file' ? 'file' : 'paste',
    source_filename: typeof payload.source_filename === 'string' && payload.source_filename.trim()
      ? payload.source_filename.trim()
      : null,
    threshold: Number.isFinite(Number(payload.threshold)) ? Number(payload.threshold) : DEFAULT_DUPLICATION_MATCH_THRESHOLD,
  };
}

async function runDuplicationDetection(user, payload) {
  ensureAuthorizedUser(user);
  const request = validateDetectionPayload(payload);
  const samples = await listCorpusSamples();

  return {
    status: samples.length > 0 ? 'completed' : 'no_samples',
    source_type: request.source_type,
    source_filename: request.source_filename,
    threshold: request.threshold,
    effective_character_count: 0,
    total_similarity_rate: 0,
    sample_count: samples.length,
    top_matches: [],
    risk: {
      score: 0,
      label: 'heuristic_only',
      explanation: '写作风险分是启发式风险提示，并非 AI 真伪结论。',
      factors: {
        paragraph_duplication_rate: 0,
        sentence_length_low_variation: 0,
        template_connector_density: 0,
        vague_phrase_density: 0,
      },
      weights: {
        paragraph_duplication_rate: 0.35,
        sentence_length_low_variation: 0.25,
        template_connector_density: 0.2,
        vague_phrase_density: 0.2,
      },
    },
  };
}

module.exports = {
  ALLOWED_DUPLICATION_DETECTION_ROLES,
  DEFAULT_DUPLICATION_MATCH_THRESHOLD,
  MAX_DUPLICATION_DETECTION_TEXT_BYTES,
  runDuplicationDetection,
};
