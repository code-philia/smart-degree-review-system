const { createHash, randomUUID } = require('crypto');
const fs = require('fs/promises');
const path = require('path');
// Runtime is Node22; this pure ESM module has no top-level await and supports
// synchronous require, keeping extraction the same synchronous public API.
const { numericDisplayFindings, referenceInfoFindings, referenceResourceMessage } =
  require('../../../shared/paper-lint-presentation.mjs');

const PROMPT_VERSION = 'report-presentation-en-v2';
const MODEL = 'qwen';
const HAN = /[\u3400-\u9fff]/;
const LITERALS = /“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|《[^》]*》|〈[^〉]*〉|"[^"\n]*"|'[^'\n]*'|[+\-−]?\d+(?:[.,:/-]\d+)*(?:[eE][+\-]?\d+)?(?:%|‰)?/g;
const MARKERS = /__P\d+__/g;
const TYPO_SOURCE = /^(?:疑似错别字|疑似错字)[：:][ \t]*([\s\S]+)$/;
const hash = value => createHash('sha256').update(value).digest('hex');
const problem = (status, message) => Object.assign(new Error(message), { status });
const rows = value => Array.isArray(value) ? value : [];

// This is an explicit presentation schema, not a recursive string translator.
// Original evidence, source locations, title, IDs, filenames and params source
// declarations must never enter the model input.
function extractTexts(result, repairs = []) {
  const values = new Set();
  const add = value => {
    if (typeof value === 'string' && value.trim() && HAN.test(value)) values.add(value);
  };
  const prose = object => {
    if (!object || typeof object !== 'object') return;
    for (const field of ['message', 'explanation', 'reason', 'suggestion', 'rationale']) add(object[field]);
  };
  const basis = items => {
    for (const item of rows(items)) {
      if (!/source|excerpt|quote|original|standard|project/i.test(item?.kind || '')) add(item?.text);
    }
  };
  const anchors = items => {
    for (const anchor of rows(items)) { add(anchor?.label); add(anchor?.description); }
  };
  prose(result?.document_validation);
  for (const rule of rows(result?.rule_runs)) {
    prose(rule);
    const derivedFindings = rule?.rule_id === 'abstract_numeric_consistency_check'
      ? numericDisplayFindings(rule)
      : rule?.rule_id === 'sjtu_rule_32' ? referenceInfoFindings(rule) : [];
    if (rule?.rule_id === 'sjtu_rule_32') add(referenceResourceMessage(rule));
    for (const finding of [...rows(rule?.findings), ...derivedFindings]) {
      prose(finding); basis(finding?.basis_details); anchors(finding?.anchors);
    }
    for (const diagnostic of rows(rule?.compiler_diagnostics)) {
      prose(diagnostic); basis(diagnostic?.basis_details);
      rows(diagnostic?.reasons).forEach(add);
    }
    // Numeric declarations, contribution texts and chapter/experiment titles are
    // original source material; only model explanations are presentation prose.
    for (const field of ['preconditions', 'numeric_results']) {
      for (const item of rows(rule?.params?.[field])) {
        add(item?.reason); add(item?.suggestion);
        anchors(item?.abstract_anchors); anchors(item?.evidence_anchors);
      }
    }
  }
  for (const review of rows(result?.finding_reviews)) add(review?.reason);
  for (const record of rows(repairs)) {
    const response = record?.response;
    prose(response);
    for (const action of rows(response?.actions)) add(action?.instruction);
    rows(response?.missing_context).forEach(add);
  }
  return [...values].sort();
}

// These are structural source fields, scoped to their own finding. Only exact
// occurrences inside an allowed explanation are protected, never guessed prose.
function extractLiteralProtections(result) {
  const protections = new Map();
  const protect = (text, literal) => {
    if (typeof text !== 'string' || typeof literal !== 'string' ||
        !literal.trim() || !text.includes(literal)) return;
    if (!protections.has(text)) protections.set(text, new Set());
    protections.get(text).add(literal);
  };
  for (const rule of rows(result?.rule_runs)) {
    for (const finding of rows(rule?.findings)) {
      const anchors = rows(finding?.anchors);
      const isSourceDescription = anchor => Boolean(anchor?.description) &&
        ((rule?.rule_id === 'typo_detection_check' && anchor?.role === 'source_span') ||
         anchor.description === anchor?.location?.text_excerpt);
      const sources = [
        finding?.location?.text_excerpt,
        ...anchors.flatMap(anchor => [
          anchor?.location?.text_excerpt,
          ...(isSourceDescription(anchor) ? [anchor.description] : []),
        ]),
        ...rows(finding?.evidence).map(item => item?.quote),
      ].filter(value => typeof value === 'string' && value.trim());
      for (const field of ['message', 'explanation', 'reason', 'suggestion', 'rationale']) {
        for (const source of sources) protect(finding?.[field], source);
      }
      // The existing typo detector's suggestion is the literal replacement,
      // whereas other rules' suggestions are explanatory instructions.
      if (rule?.rule_id === 'typo_detection_check') protect(finding?.suggestion, finding?.suggestion);
      for (const anchor of anchors) {
        if (isSourceDescription(anchor)) {
          protect(anchor?.description, anchor?.description);
        }
      }
    }
  }
  return new Map([...protections].map(([text, values]) => [text, [...values].sort()]));
}

function protectText(original, sourceLiterals = []) {
  if (/__P\d+__/.test(original)) throw new Error('source contains a reserved translation marker');
  const spans = [];
  for (const match of original.matchAll(LITERALS)) spans.push([match.index, match.index + match[0].length]);
  // run_bilingual_semantic_lint.py emits this exact prefix followed solely by
  // the suspect original span; preserve the whole suffix, including newlines.
  const typo = TYPO_SOURCE.exec(original);
  if (typo) spans.push([original.length - typo[1].length, original.length]);
  for (const literal of sourceLiterals) {
    if (typeof literal !== 'string' || !literal.length) continue;
    let start = original.indexOf(literal);
    while (start >= 0) {
      spans.push([start, start + literal.length]);
      start = original.indexOf(literal, start + literal.length);
    }
  }
  spans.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const merged = [];
  for (const span of spans) {
    const previous = merged[merged.length - 1];
    if (previous && span[0] < previous[1]) previous[1] = Math.max(previous[1], span[1]);
    else merged.push([...span]);
  }
  const tokens = [];
  let text = '', offset = 0;
  for (const [start, end] of merged) {
    text += original.slice(offset, start) + '__P' + tokens.length + '__';
    tokens.push(original.slice(start, end));
    offset = end;
  }
  text += original.slice(offset);
  return { text, tokens };
}

function validateAnswer(answer, items) {
  if (!answer || typeof answer !== 'object' || Array.isArray(answer) ||
      Object.keys(answer).join(',') !== 'items' || !Array.isArray(answer.items) ||
      answer.items.length !== items.length) throw new Error('invalid translation envelope');
  const byId = new Map(items.map(item => [item.id, item]));
  const outputs = new Map();
  for (const row of answer.items) {
    if (!row || Object.keys(row).sort().join(',') !== 'id,text' ||
        !byId.has(row.id) || outputs.has(row.id) || typeof row.text !== 'string' ||
        !row.text.trim() || row.text.length > 24000) throw new Error('invalid translation item');
    const item = byId.get(row.id);
    let text = row.text.trim();
    const markers = text.match(MARKERS) || [];
    if (markers.length !== item.tokens.length ||
        item.tokens.some((_, index) => markers.filter(marker => marker === '__P' + index + '__').length !== 1)) {
      throw new Error('translation changed protected literals');
    }
    const prose = text.replace(MARKERS, '');
    if (/\d/.test(prose) || HAN.test(prose) || /__P|__\d/.test(prose)) {
      throw new Error('translation changed numbers or left untranslated prose');
    }
    text = text.replace(MARKERS, marker => item.tokens[Number(marker.slice(3, -2))]);
    outputs.set(row.id, text);
  }
  return items.map(item => outputs.get(item.id));
}

function runModel(items) {
  const { execFile } = require('child_process');
  const configuredTimeout = Number(process.env.REPORT_TRANSLATION_TIMEOUT_MS);
  const timeout = Number.isFinite(configuredTimeout) && configuredTimeout >= 1000
    ? Math.min(65000, configuredTimeout) : 65000;
  return new Promise((resolve, reject) => {
    const child = execFile(
      process.env.REPORT_TRANSLATION_PYTHON || process.env.REPAIR_MODEL_PYTHON || process.env.SIX_RULE_PYTHON || 'python3',
      [path.resolve(__dirname, '../../scripts/report_translation.py')],
      { timeout, maxBuffer: 1024 * 1024, encoding: 'utf8',
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' } },
      (error, stdout) => {
        let output;
        try { output = JSON.parse(stdout); } catch { reject(new Error('translation unavailable')); return; }
        if (error || output.status === 'error') reject(new Error('translation unavailable'));
        else resolve(output);
      },
    );
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ items }));
  });
}

// Shared across service instances/resources. Reject excess work promptly so
// translation cannot accumulate unbounded child processes or stall detection.
const modelFlights = new Map();
function runBoundedModel(items) {
  const key = hash(JSON.stringify(items));
  if (modelFlights.has(key)) return modelFlights.get(key);
  if (modelFlights.size >= 2) return Promise.reject(new Error('translation capacity busy'));
  const flight = runModel(items).finally(() => modelFlights.delete(key));
  modelFlights.set(key, flight);
  return flight;
}

function cacheDirectory() {
  return process.env.REPORT_TRANSLATION_CACHE_DIR ||
    path.join(process.env.PAPER_COMPILER_CACHE_ROOT || '/data/runtime/paper-compiler', 'report-presentation-translations');
}

function createTranslationService({
  cacheDir,
  loadReport = (...args) => require('./paperLintReportRepository').findPaperLintReportByIdForUser(...args),
  loadJob = (...args) => require('./paperLintJobRepository').getJobForUser(...args),
  loadRepairs = args => require('./paperLintRepairSuggestionService').listPaperLintRepairSuggestionRecords(args),
  model = runBoundedModel, batchItems = 24, batchChars = 6000, maxBatches = 2,
} = {}) {
  const flights = new Map();
  async function translate({ reportId, jobId, userId, locale }) {
    if (locale !== 'en' || !userId || Boolean(reportId) === Boolean(jobId)) throw problem(400, 'Invalid translation request');
    // Authorization and current snapshot lookup always precede any cache read,
    // including in-flight reuse, and apply equally to completed/live resources.
    let report;
    let result;
    let savedId = reportId;
    if (reportId) {
      report = await loadReport(reportId, userId);
      if (!report) throw problem(404, 'Report not found');
      result = report.result;
    } else {
      const job = await loadJob(jobId, userId);
      if (!job) throw problem(404, 'Job not found');
      result = job.progress;
      savedId = job.report_id;
      if (savedId) {
        report = await loadReport(savedId, userId);
        if (!report) throw problem(404, 'Report not found');
        result = report.result;
      }
    }
    const repairs = savedId ? await loadRepairs({ reportId: savedId, userId }) : [];
    const texts = extractTexts(result, repairs);
    const protections = extractLiteralProtections(result);
    const protectionIdentity = [...protections].sort(([left], [right]) => left.localeCompare(right));
    const sourceHash = hash(JSON.stringify(protectionIdentity.length ? { texts, protections: protectionIdentity } : texts));
    const identity = JSON.stringify([userId, reportId || jobId, sourceHash, locale,
      MODEL, process.env.REPORT_TRANSLATION_MODEL || MODEL,
      process.env.REPORT_TRANSLATION_MODEL_VERSION || 'campus-current', PROMPT_VERSION]);
    if (flights.has(identity)) return flights.get(identity);
    const flight = generate(texts, userId, sourceHash, protections).finally(() => flights.delete(identity));
    flights.set(identity, flight);
    return flight;
  }
  async function generate(texts, userId, sourceHash, protections) {
    const translations = Object.create(null);
    const missing = [];
    const root = cacheDir || cacheDirectory();
    for (const original of texts) {
      let protectedText;
      try { protectedText = protectText(original, protections.get(original)); } catch { continue; }
      // Pure source/replacement strings are already complete presentation
      // literals. Never send them to a translation model or replay old prose.
      if (!HAN.test(protectedText.text)) {
        translations[original] = original;
        continue;
      }
      const defaultProtection = protectText(original);
      const contextual = TYPO_SOURCE.test(original) || protectedText.text !== defaultProtection.text ||
        JSON.stringify(protectedText.tokens) !== JSON.stringify(defaultProtection.tokens);
      const identity = [userId, original, 'en', MODEL,
        process.env.REPORT_TRANSLATION_MODEL || MODEL,
        process.env.REPORT_TRANSLATION_MODEL_VERSION || 'campus-current', PROMPT_VERSION];
      // A string with a source span and the same prose without source
      // provenance must not share a semantically different masked cache entry.
      if (contextual) identity.push({ source_protection: protectedText });
      const key = hash(JSON.stringify(identity));
      const file = path.join(root, key.slice(0, 2), key + '.json');
      try {
        const cached = JSON.parse(await fs.readFile(file, 'utf8'));
        if (cached.key !== key) throw new Error('invalid cache identity');
        const restored = validateAnswer({ items: [{ id: 'cache', text: cached.text }] }, [{ id: 'cache', ...protectedText }])[0];
        translations[original] = restored;
      } catch {
        missing.push({ original, file, key, ...protectedText });
      }
    }
    let batches = 0;
    while (missing.length && batches < maxBatches) {
      const batch = [];
      let chars = 0;
      while (missing.length && batch.length < batchItems) {
        const item = missing[0];
        if (item.text.length > batchChars) { missing.shift(); continue; }
        if (batch.length && chars + item.text.length > batchChars) break;
        missing.shift(); chars += item.text.length;
        batch.push({ ...item, id: 'i' + batch.length });
      }
      if (!batch.length) break;
      batches++;
      try {
        const answer = await model(batch.map(({id, text}) => ({id, text})));
        const restored = validateAnswer(answer, batch);
        for (const [index, item] of batch.entries()) {
          translations[item.original] = restored[index];
          // Persist the validated masked answer, not canonical report data.
          const masked = answer.items.find(row => row.id === item.id).text.trim();
          const temporary = item.file + '.' + randomUUID() + '.tmp';
          try {
            await fs.mkdir(path.dirname(item.file), { recursive: true, mode: 0o700 });
            await fs.writeFile(temporary, JSON.stringify({ key: item.key, text: masked }), { flag: 'wx', mode: 0o600 });
            await fs.rename(temporary, item.file);
          } catch {
            await fs.rm(temporary, { force: true }).catch(() => {});
          }
        }
      } catch {
        // A failed batch is never persisted. Earlier fully validated batches
        // remain available and the next explicit request retries missing work.
        break;
      }
    }
    const count = Object.keys(translations).length;
    const status = count === texts.length ? 'ready' : count ? 'partial' : 'unavailable';
    return { locale: 'en', status, translations, source_hash: sourceHash, model: MODEL,
      ...(status === 'ready' ? {} : { message: 'Some explanations are not translated yet. Retry to continue; the original report remains available.' }) };
  }
  return translate;
}

module.exports = { PROMPT_VERSION, extractTexts, extractLiteralProtections, protectText, validateAnswer, runModel, createTranslationService };
