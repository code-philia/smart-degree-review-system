const { listCorpusSamples } = require('./duplicationCorpusRepository');

const MAX_DUPLICATION_DETECTION_TEXT_BYTES = 5 * 1024 * 1024;
const DEFAULT_DUPLICATION_MATCH_THRESHOLD = 0.65;
const ALLOWED_DUPLICATION_DETECTION_ROLES = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];
const RISK_WEIGHTS = {
  paragraph_duplication_rate: 0.35,
  sentence_length_low_variation: 0.25,
  template_connector_density: 0.2,
  vague_phrase_density: 0.2,
};
const TEMPLATE_CONNECTORS = [
  '首先',
  '其次',
  '再次',
  '最后',
  '因此',
  '综上所述',
  '总之',
  '与此同时',
  'however',
  'therefore',
  'moreover',
  'firstly',
  'secondly',
];
const VAGUE_PHRASES = [
  '相关问题',
  '相关方面',
  '相关单位',
  '具有重要意义',
  '应予以重视',
  '进一步完善',
  '提升协同',
  '一定程度',
  'somewhat',
  'various',
  'important',
];

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

  const threshold = Number.isFinite(Number(payload.threshold))
    ? Math.min(1, Math.max(0, Number(payload.threshold)))
    : DEFAULT_DUPLICATION_MATCH_THRESHOLD;

  return {
    text,
    source_type: payload.source_type === 'file' ? 'file' : 'paste',
    source_filename: typeof payload.source_filename === 'string' && payload.source_filename.trim()
      ? payload.source_filename.trim()
      : null,
    threshold,
  };
}

function normalizeText(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/\s+/gu, ' ')
    .replace(/[\p{P}\p{S}]/gu, '')
    .trim();
}

function buildCharacterNgrams(text, size = 5) {
  const normalized = normalizeText(text);
  if (!normalized) {
    return new Set();
  }
  if ([...normalized].length <= size) {
    return new Set([normalized]);
  }

  const chars = [...normalized];
  const grams = new Set();
  for (let index = 0; index <= chars.length - size; index += 1) {
    grams.add(chars.slice(index, index + size).join(''));
  }
  return grams;
}

function jaccardScore(leftText, rightText) {
  const left = buildCharacterNgrams(leftText);
  const right = buildCharacterNgrams(rightText);
  if (left.size === 0 && right.size === 0) {
    return 1;
  }
  if (left.size === 0 || right.size === 0) {
    return 0;
  }

  let intersection = 0;
  for (const gram of left) {
    if (right.has(gram)) {
      intersection += 1;
    }
  }
  const union = left.size + right.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

function splitParagraphsWithSpans(text) {
  const paragraphs = [];
  const pattern = /[^\n]+/gu;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const raw = match[0];
    const leadingWhitespace = raw.match(/^\s*/u)?.[0].length || 0;
    const trailingWhitespace = raw.match(/\s*$/u)?.[0].length || 0;
    const value = raw.slice(leadingWhitespace, raw.length - trailingWhitespace);
    if (value.trim()) {
      paragraphs.push({
        text: value,
        start: match.index + leadingWhitespace,
        end: match.index + raw.length - trailingWhitespace,
      });
    }
  }
  return paragraphs;
}

function createSegments(sourceText, sampleText, threshold) {
  const sourceParagraphs = splitParagraphsWithSpans(sourceText);
  const sampleParagraphs = splitParagraphsWithSpans(sampleText);
  const segments = [];

  for (const sourceParagraph of sourceParagraphs) {
    let best = null;
    for (const sampleParagraph of sampleParagraphs) {
      const score = jaccardScore(sourceParagraph.text, sampleParagraph.text);
      if (!best || score > best.score) {
        best = { sampleParagraph, score };
      }
    }
    if (best && best.score >= threshold) {
      segments.push({
        source_start: sourceParagraph.start,
        source_end: sourceParagraph.end,
        sample_start: best.sampleParagraph.start,
        sample_end: best.sampleParagraph.end,
        source_excerpt: sourceParagraph.text,
        sample_excerpt: best.sampleParagraph.text,
        score: best.score,
      });
    }
  }

  return segments;
}

function mergeIntervals(intervals) {
  const sorted = intervals
    .filter((interval) => interval.end > interval.start)
    .sort((left, right) => left.start - right.start || left.end - right.end);
  const merged = [];
  for (const interval of sorted) {
    const last = merged[merged.length - 1];
    if (!last || interval.start > last.end) {
      merged.push({ ...interval });
    } else {
      last.end = Math.max(last.end, interval.end);
    }
  }
  return merged;
}

function countMergedCharacters(intervals) {
  return mergeIntervals(intervals).reduce((total, interval) => total + interval.end - interval.start, 0);
}

function roundNumber(value, digits = 6) {
  return Number(value.toFixed(digits));
}

function countPhraseHits(text, phrases) {
  const normalized = text.toLowerCase();
  return phrases.reduce((total, phrase) => {
    const matches = normalized.match(new RegExp(phrase, 'gu'));
    return total + (matches ? matches.length : 0);
  }, 0);
}

function splitSentences(text) {
  return text
    .split(/[。！？.!?；;\n]+/u)
    .map((sentence) => normalizeText(sentence))
    .filter(Boolean);
}

function calculateWritingRisk(text, totalSimilarityRate) {
  const paragraphs = splitParagraphsWithSpans(text).map((paragraph) => normalizeText(paragraph.text)).filter(Boolean);
  const repeatedParagraphs = paragraphs.filter((paragraph, index) => paragraphs.indexOf(paragraph) !== index).length;
  const paragraphDuplicationRate = Math.min(100, totalSimilarityRate * 100 + (paragraphs.length ? (repeatedParagraphs / paragraphs.length) * 100 : 0));

  const sentenceLengths = splitSentences(text).map((sentence) => [...sentence].length);
  const averageLength = sentenceLengths.length
    ? sentenceLengths.reduce((total, length) => total + length, 0) / sentenceLengths.length
    : 0;
  const variance = sentenceLengths.length
    ? sentenceLengths.reduce((total, length) => total + ((length - averageLength) ** 2), 0) / sentenceLengths.length
    : 0;
  const coefficient = averageLength > 0 ? Math.sqrt(variance) / averageLength : 1;
  const sentenceLengthLowVariation = sentenceLengths.length > 1 ? Math.max(0, Math.min(100, (1 - coefficient) * 100)) : 0;

  const effectiveLength = Math.max([...normalizeText(text)].length, 1);
  const templateConnectorDensity = Math.min(100, (countPhraseHits(text, TEMPLATE_CONNECTORS) / effectiveLength) * 900);
  const vaguePhraseDensity = Math.min(100, (countPhraseHits(text, VAGUE_PHRASES) / effectiveLength) * 1200);
  const factors = {
    paragraph_duplication_rate: roundNumber(paragraphDuplicationRate, 5),
    sentence_length_low_variation: roundNumber(sentenceLengthLowVariation, 5),
    template_connector_density: roundNumber(templateConnectorDensity, 5),
    vague_phrase_density: roundNumber(vaguePhraseDensity, 5),
  };
  const score = Object.entries(RISK_WEIGHTS).reduce((total, [key, weight]) => total + factors[key] * weight, 0);

  return {
    score: roundNumber(score, 5),
    label: 'heuristic_only',
    explanation: '写作风险分是启发式风险提示，并非 AI 真伪结论。',
    factors,
    weights: RISK_WEIGHTS,
  };
}

async function runDuplicationDetection(user, payload) {
  ensureAuthorizedUser(user);
  const request = validateDetectionPayload(payload);
  const samples = await listCorpusSamples();
  const normalizedSource = normalizeText(request.text);
  const effectiveCharacterCount = [...normalizedSource].length;
  const sourceIntervals = [];

  const matches = samples
    .map((sample) => {
      const globalScore = jaccardScore(request.text, sample.content);
      const segmentsWithScores = createSegments(request.text, sample.content, request.threshold);
      const segmentScore = segmentsWithScores.reduce((highest, segment) => Math.max(highest, segment.score), 0);
      const jaccard = Math.max(globalScore, segmentScore);
      const segments = segmentsWithScores.map(({ score, ...segment }) => segment);
      const matchedCharacterCount = countMergedCharacters(segments.map((segment) => ({ start: segment.source_start, end: segment.source_end })));
      return {
        sample_id: sample.id,
        title: sample.title,
        subject: sample.subject,
        year: sample.year,
        jaccard_score: roundNumber(jaccard, 6),
        matched_character_count: matchedCharacterCount,
        segments,
      };
    })
    .filter((match) => match.jaccard_score >= request.threshold)
    .sort((left, right) => right.jaccard_score - left.jaccard_score)
    .slice(0, 5);

  for (const match of matches) {
    for (const segment of match.segments) {
      sourceIntervals.push({ start: segment.source_start, end: segment.source_end });
    }
  }

  const matchedCharacters = countMergedCharacters(sourceIntervals);
  const totalSimilarityRate = effectiveCharacterCount > 0 ? Math.min(1, matchedCharacters / effectiveCharacterCount) : 0;

  return {
    status: samples.length > 0 && matches.length > 0 ? 'completed' : samples.length > 0 ? 'completed' : 'no_samples',
    source_type: request.source_type,
    source_filename: request.source_filename,
    threshold: request.threshold,
    effective_character_count: effectiveCharacterCount,
    total_similarity_rate: roundNumber(totalSimilarityRate, 6),
    sample_count: samples.length,
    top_matches: matches,
    risk: calculateWritingRisk(request.text, totalSimilarityRate),
  };
}

module.exports = {
  ALLOWED_DUPLICATION_DETECTION_ROLES,
  DEFAULT_DUPLICATION_MATCH_THRESHOLD,
  MAX_DUPLICATION_DETECTION_TEXT_BYTES,
  runDuplicationDetection,
};
