const { execFile } = require('child_process');
const { createHash } = require('crypto');
const fs = require('fs');
const path = require('path');

const SCRIPT = path.resolve(__dirname, '../../scripts/pdf_evidence_locations.py');
const RULES = new Set(['bilingual_keywords_correspondence_check', 'bilingual_abstract_consistency_check']);

function resolvePython() {
  return process.env.PAPER_LINT_EVIDENCE_PYTHON || process.env.PAPER_MODEL_PYTHON
    || process.env.FIVE_RULE_PYTHON || process.env.SIX_RULE_PYTHON || 'python3';
}

function extractLocations(pdfPath, queries) {
  return new Promise((resolve, reject) => {
    const child = execFile(resolvePython(), [SCRIPT, pdfPath], {
      timeout: 10000, maxBuffer: 1024 * 1024, killSignal: 'SIGKILL',
      encoding: 'utf8', windowsHide: true, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    }, (error, stdout) => {
      if (error) return reject(error);
      try { resolve(JSON.parse(stdout).locations); } catch (cause) { reject(cause); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ queries }));
  });
}

async function fingerprint(pdfPath) {
  const stat = await fs.promises.stat(pdfPath);
  if (!stat.isFile()) throw new Error('PDF unavailable');
  return [stat.dev, stat.ino, stat.size, stat.mtimeMs, stat.ctimeMs].join(':');
}

function validLocation(location, query) {
  const validRect = rect => rect && ['x1', 'y1', 'x2', 'y2', 'width', 'height'].every(key => Number.isFinite(rect[key]))
    && rect.width > 0 && rect.height > 0 && rect.x2 > rect.x1 && rect.y2 > rect.y1
    && Number.isSafeInteger(rect.page_number) && rect.page_number >= query.page_number
    && rect.page_number < query.page_number + query.page_count;
  return location?.type === 'pdf_bbox' && location.text_excerpt === query.quote
    && validRect(location.bounding_rect) && location.page_number === location.bounding_rect.page_number
    && Array.isArray(location.rects) && location.rects.length > 0 && location.rects.every(validRect);
}

function createEvidenceLocationService({ extract = extractLocations, maxEntries = 32 } = {}) {
  // Cache only geometry. Keys include source identity and the exact evidence
  // requests; saved result objects and user data never enter the cache.
  const cache = new Map();
  const inFlight = new Map();
  async function locationsFor(pdfPath, queries) {
    const source = await fingerprint(pdfPath);
    const key = [path.resolve(pdfPath), source,
      createHash('sha256').update(JSON.stringify(queries)).digest('hex')].join(':');
    if (cache.has(key)) {
      const value = cache.get(key);
      cache.delete(key);
      cache.set(key, value);
      return value;
    }
    if (inFlight.has(key)) return inFlight.get(key);
    if (inFlight.size >= maxEntries) return null;
    const pending = (async () => {
      const locations = await extract(pdfPath, queries);
      if (!Array.isArray(locations) || locations.length !== queries.length) return null;
      if (source !== await fingerprint(pdfPath)) return null;
      cache.set(key, locations);
      while (cache.size > maxEntries) cache.delete(cache.keys().next().value);
      return locations;
    })();
    inFlight.set(key, pending);
    try { return await pending; }
    finally { inFlight.delete(key); }
  }

  async function hydratePaperLintEvidenceLocations(result, pdfPath) {
    const targets = [];
    for (const run of result.rule_runs || []) {
      if (!RULES.has(run.rule_id)) continue;
      for (const finding of run.findings || []) {
        for (const anchor of finding.anchors || []) {
          const location = anchor.location;
          if (anchor.role !== 'source_span' || location?.type !== 'pdf_page'
            || !Number.isSafeInteger(location.page_number) || location.page_number < 1) continue;
          const evidence = finding.evidence?.find(row => row.id === anchor.anchor_id && row.kind === 'source_span');
          const quote = String(evidence?.quote || location.text_excerpt || '').trim();
          if (!quote || quote.length > 6000 || targets.length >= 100) continue;
          targets.push({ finding, anchor, original: location, query: {
            page_number: location.page_number, quote,
            page_count: run.rule_id === 'bilingual_keywords_correspondence_check' ? 1 : 3,
          } });
        }
      }
    }
    if (!targets.length || !pdfPath) return result;
    try {
      const locations = await locationsFor(pdfPath, targets.map(target => target.query));
      for (const [index, target] of targets.entries()) {
        const location = locations?.[index];
        if (!validLocation(location, target.query)) continue;
        target.anchor.location = structuredClone(location);
        const primary = target.finding.location;
        if (primary?.type === 'pdf_page' && primary.page_number === target.original.page_number
          && primary.text_excerpt === target.original.text_excerpt) {
          target.finding.location = structuredClone(location);
        }
      }
    } catch {
      // Optional historical projection: unavailable evidence retains page-only
      // navigation; reading a report never requires rewriting or rerunning it.
    }
    return result;
  }
  return { hydratePaperLintEvidenceLocations };
}

module.exports = { ...createEvidenceLocationService(), createEvidenceLocationService };
