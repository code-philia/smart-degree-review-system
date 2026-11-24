'use strict';

// Identifier-first, multi-catalog metadata comparison, inspired by RefChecker:
// https://github.com/markrussinovich/refchecker/tree/27a81896c0c3d7361fb95b4d14b24a86f02c9c0d
// Independent implementation; no upstream code or model calls. Optional personal
// Scholar search is supplementary and never establishes nonexistence.
const { createHash } = require('node:crypto');
const { personalReferenceCredentials } = require('../auth/referencePersonalAccess');

const REQUEST_TIMEOUT_MS = 4500;
const TOTAL_TIMEOUT_MS = 18000;
const MAX_BODY_BYTES = 1024 * 1024;
const CACHE_TTL_MS = 5 * 60 * 1000;
const CACHE_LIMIT = 256;
const caches = new WeakMap();
const pacing = new WeakMap();
const cooldowns = new WeakMap();

function abortError() {
  const error = new Error('Reference verification cancelled');
  error.name = 'AbortError';
  return error;
}
function checkAbort(signal) { if (signal?.aborted) throw abortError(); }
function clean(value, limit = 2000) {
  return typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, limit) : '';
}
function decodeEntities(value) {
  return value.replace(/&(?:amp|lt|gt|quot|apos|#\d+|#x[\da-f]+);/gi, token => {
    const named = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'" };
    if (named[token]) return named[token];
    const n = token[2].toLowerCase() === 'x' ? parseInt(token.slice(3, -1), 16) : parseInt(token.slice(2, -1), 10);
    return n > 0 && n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff) ? String.fromCodePoint(n) : '';
  });
}
function normalizeDoi(value) {
  let doi = clean(value, 300).replace(/^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi\s*:\s*)/i, '');
  try { doi = decodeURIComponent(doi); } catch { return null; }
  doi = doi.replace(/[.,;]+$/, '').toLowerCase();
  if (doi.endsWith(')') && (doi.match(/\)/g) || []).length > (doi.match(/\(/g) || []).length) doi = doi.slice(0, -1);
  return /^10\.\d{4,9}\/[^\s<>"?#]+$/i.test(doi) && doi.length <= 240 ? doi : null;
}
function normalizeArxiv(value) {
  const id = clean(value, 150).replace(/^(?:arxiv\s*:\s*|https?:\/\/(?:export\.)?arxiv\.org\/(?:abs|pdf)\/)/i, '')
    .replace(/\.pdf$/i, '').replace(/v\d+$/i, '').toLowerCase();
  return /^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?\/\d{7})$/.test(id) ? id : null;
}
function arxivFromDoi(doi) {
  return doi?.startsWith('10.48550/arxiv.') ? normalizeArxiv(doi.slice('10.48550/arxiv.'.length)) : null;
}
function titleKey(value) {
  return decodeEntities(clean(value).replace(/<[^>]*>/g, '')).normalize('NFKD').replace(/\p{M}/gu, '')
    .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ');
}
function strongTitle(a, b) {
  const x = titleKey(a), y = titleKey(b);
  if (!x || !y) return false;
  if (x === y) return x.length >= 12;
  if (Math.min(x.length, y.length) < 25) return false;
  const xt = new Set(x.split(' ')), yt = new Set(y.split(' '));
  const common = [...xt].filter(t => yt.has(t)).length;
  // Omitted subtitle words are not enough; require almost the whole title.
  if (common / Math.max(xt.size, yt.size) < 0.9) return false;
  const bigrams = s => new Set(Array.from({ length: s.length - 1 }, (_, i) => s.slice(i, i + 2)));
  const xb = bigrams(x), yb = bigrams(y);
  return 2 * [...xb].filter(t => yb.has(t)).length / (xb.size + yb.size) >= 0.93;
}
function authorParts(name) {
  const comma = name.includes(',');
  const parts = titleKey(name).split(' ').filter(p => !['et', 'al', 'and', 'jr'].includes(p));
  if (!parts.length) return null;
  let suffixStart = parts.length;
  while (suffixStart > 1 && parts[suffixStart - 1].length === 1) suffixStart--;
  const surname = comma ? titleKey(name.split(',')[0]).split(' ').at(-1)
    : suffixStart < parts.length ? parts[suffixStart - 1] : parts.at(-1);
  const initial = comma ? titleKey(name.split(',').slice(1).join(' '))[0]
    : suffixStart < parts.length ? parts[suffixStart][0] : parts.length > 1 ? parts[0][0] : null;
  return { surname, initial, key: [...parts].sort().join(' ') };
}
function authorMatch(left, right) {
  const a = left.map(authorParts).filter(Boolean), b = right.map(authorParts).filter(Boolean);
  if (!a.length || !b.length) return null;
  const x = a[0], y = b[0];
  return x.key === y.key || (x.surname === y.surname && (!x.initial || !y.initial || x.initial === y.initial));
}
function hanLatinDifference(left, right) {
  const a = clean(left), b = clean(right);
  const aHan = /\p{Script=Han}/u.test(a), bHan = /\p{Script=Han}/u.test(b);
  return aHan !== bHan && (aHan ? /\p{Script=Latin}/u.test(b) : /\p{Script=Latin}/u.test(a));
}
function yearValue(value) { return Number.isInteger(value) && value >= 1500 && value <= 2200 ? value : null; }
function normalizeEntry(entry) {
  const doi = normalizeDoi(entry?.doi);
  const arxiv_id = normalizeArxiv(entry?.arxiv_id) || arxivFromDoi(doi);
  return {
    title: clean(entry?.title), authors: Array.isArray(entry?.authors) ? entry.authors.slice(0, 30).map(a => clean(a, 150)).filter(Boolean) : [],
    year: yearValue(entry?.year), doi, arxiv_id,
    has_doi: Boolean(clean(entry?.doi)), has_arxiv: Boolean(clean(entry?.arxiv_id) || arxiv_id),
    type_code: clean(entry?.type_code, 20).toUpperCase(), extraction_confidence: entry?.extraction_confidence === 'high' ? 'high' : 'partial',
  };
}
function doiUrl(doi) { return `https://doi.org/${doi.split('/').map(encodeURIComponent).join('/')}`; }
function arxivUrl(id) { return `https://arxiv.org/abs/${id}`; }
function sanitizeRecord(record, secrets) {
  const redact = text => secrets.reduce((value, secret) => value.split(secret).join('[redacted]'), text);
  return {
    ...record,
    title: redact(record.title), authors: record.authors.map(redact),
    // URLs and identifiers are constructed solely from validated catalog fields.
    doi: record.doi && !secrets.some(key => record.doi.includes(key)) ? record.doi : null,
    related_doi: record.related_doi && !secrets.some(key => record.related_doi.includes(key)) ? record.related_doi : null,
    url: secrets.some(key => record.url.includes(key)) ? null : record.url,
  };
}
function openalexRecord(value) {
  if (!value || typeof value !== 'object' || !clean(value.title || value.display_name)) return null;
  const doi = normalizeDoi(value.doi), aid = normalizeArxiv(value.ids?.arxiv);
  const workId = /^https:\/\/openalex\.org\/W\d+$/i.test(value.id || '') ? value.id.replace(/^http:/, 'https:') : null;
  if (!doi && !workId && !aid) return null;
  return { title: clean(value.title || value.display_name), authors: (Array.isArray(value.authorships) ? value.authorships : []).slice(0, 30).map(a => clean(a.author?.display_name, 150)).filter(Boolean),
    year: yearValue(value.publication_year), doi, arxiv_id: aid, type: clean(value.type, 50), provider: 'openalex',
    url: doi ? doiUrl(doi) : aid ? arxivUrl(aid) : workId, related_doi: null };
}
function crossrefRecord(value) {
  const doi = normalizeDoi(value?.DOI), title = clean(Array.isArray(value?.title) ? value.title[0] : value?.title);
  if (!doi || !title) return null;
  const dates = [value.published, value['published-print'], value['published-online'], value.issued];
  const year = dates.map(d => yearValue(d?.['date-parts']?.[0]?.[0])).find(Boolean) || null;
  const related = value.relation?.['is-preprint-of'] || [];
  return { title, doi, arxiv_id: null, year, provider: 'crossref', type: clean(value.type, 50), url: doiUrl(doi),
    authors: (Array.isArray(value.author) ? value.author : []).slice(0, 30).map(a => clean([a.given, a.family].filter(Boolean).join(' ') || a.name, 150)).filter(Boolean),
    related_doi: normalizeDoi(related.find(r => r['id-type'] === 'doi')?.id) };
}
function parseArxiv(text) {
  // No XML engine, DTD, external entities or remote expansion. Only the small Atom subset is read.
  if (/<!DOCTYPE|<!ENTITY/i.test(text) || !/<(?:\w+:)?feed\b[^>]*>[\s\S]*<\/(?:\w+:)?feed\s*>/i.test(text)) throw new Error('invalid_payload');
  const entries = [...text.matchAll(/<(?:\w+:)?entry\b[^>]*>([\s\S]*?)<\/(?:\w+:)?entry\s*>/gi)];
  if ((text.match(/<(?:\w+:)?entry\b/gi) || []).length !== entries.length) throw new Error('invalid_payload');
  const tag = (source, name) => {
    const value = source.match(new RegExp(`<(?:\\w+:)?${name}\\b[^>]*>([\\s\\S]*?)<\\/(?:\\w+:)?${name}\\s*>`, 'i'))?.[1] || '';
    return clean(decodeEntities(value.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1').replace(/<[^>]*>/g, '')));
  };
  return entries.slice(0, 5).map(entry => {
    const source = entry[1], id = normalizeArxiv(tag(source, 'id')), title = tag(source, 'title');
    if (!id || !title) throw new Error('invalid_payload');
    return { title, arxiv_id: id, doi: null, related_doi: normalizeDoi(tag(source, 'doi')), provider: 'arxiv', type: 'preprint',
      year: yearValue(Number(tag(source, 'published').slice(0, 4))),
      authors: [...source.matchAll(/<(?:\w+:)?author\b[^>]*>([\s\S]*?)<\/(?:\w+:)?author\s*>/gi)].slice(0, 30).map(a => tag(a[1], 'name')).filter(Boolean), url: arxivUrl(id) };
  });
}
function wait(ms, signal) {
  checkAbort(signal);
  return new Promise((resolve, reject) => {
    const done = () => { signal?.removeEventListener('abort', cancel); resolve(); };
    const timer = setTimeout(done, ms);
    const cancel = () => { clearTimeout(timer); reject(abortError()); };
    signal?.addEventListener('abort', cancel, { once: true });
  });
}
async function readBody(response) {
  if (Number(response.headers?.get('content-length')) > MAX_BODY_BYTES) throw new Error('invalid_payload');
  if (!response.body?.getReader) {
    const body = await response.text();
    if (Buffer.byteLength(body) > MAX_BODY_BYTES) throw new Error('invalid_payload');
    return body;
  }
  const reader = response.body.getReader();
  const chunks = []; let length = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_BODY_BYTES) throw new Error('invalid_payload');
      chunks.push(Buffer.from(value));
    }
    return Buffer.concat(chunks).toString('utf8');
  } finally { void reader.cancel().catch(() => {}); }
}
function retryAfter(response) {
  const value = response.headers?.get('retry-after');
  if (!value) return 250;
  if (/^\d+(?:\.\d+)?$/.test(value)) return Number(value) * 1000;
  const time = Date.parse(value);
  return Number.isFinite(time) ? Math.max(0, time - Date.now()) : 250;
}
async function pace(url, context) {
  // arXiv asks clients to leave three seconds between API requests. Keep other
  // catalogs below the unauthenticated OpenAlex rate as well, across references.
  const interval = url.hostname === 'export.arxiv.org' ? 3000 : 100;
  let slots = pacing.get(context.fetchImpl);
  if (!slots) { slots = new Map(); pacing.set(context.fetchImpl, slots); }
  const blockedUntil = () => cooldowns.get(context.fetchImpl)?.get(url.hostname) || 0;
  const now = Date.now(), next = Math.max(now, slots.get(url.hostname) || 0, blockedUntil());
  if (next >= context.deadline) return false;
  slots.set(url.hostname, next + interval);
  if (next > now) await wait(next - now, context.signal);
  // A different in-flight reference can receive a Retry-After while this one
  // waits for its slot. Recheck the shared cooldown before issuing the request.
  while (blockedUntil() > Date.now()) {
    const until = blockedUntil();
    if (until >= context.deadline) return false;
    await wait(until - Date.now(), context.signal);
  }
  return true;
}
function coolDown(url, context, delay) {
  let providers = cooldowns.get(context.fetchImpl);
  if (!providers) { providers = new Map(); cooldowns.set(context.fetchImpl, providers); }
  providers.set(url.hostname, Math.max(providers.get(url.hostname) || 0, Date.now() + delay));
}
async function request(url, context, { credentialFallback = false, maxAttempts = 2 } = {}) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    checkAbort(context.signal);
    if (!await pace(url, context)) return { status: 'timeout' };
    checkAbort(context.signal);
    const remaining = context.deadline - Date.now();
    if (remaining <= 0) return { status: 'timeout' };
    const controller = new AbortController();
    let timer, abortListener;
    const stopped = new Promise((_, reject) => {
      timer = setTimeout(() => { controller.abort(); reject(new Error('timeout')); }, Math.min(REQUEST_TIMEOUT_MS, remaining));
      abortListener = () => { controller.abort(); reject(abortError()); };
      context.signal?.addEventListener('abort', abortListener, { once: true });
    });
    let response, body;
    try {
      const result = await Promise.race([
        (async () => {
          const fetched = await context.fetchImpl(url.toString(), { signal: controller.signal, redirect: 'error',
            headers: { accept: 'application/json, application/atom+xml;q=0.9', 'user-agent': 'AcademicReferenceVerifier/1.0' } });
          return { response: fetched, body: fetched.ok || fetched.status === 429 ? await readBody(fetched) : '' };
        })(), stopped,
      ]);
      ({ response, body } = result);
    } catch (error) {
      checkAbort(context.signal);
      if (attempt + 1 < maxAttempts && error.message !== 'invalid_payload' && context.deadline - Date.now() > 300) {
        // The retry is bounded even if a fetch implementation ignores cancellation.
        controller.abort();
        await wait(250, context.signal);
        continue;
      }
      return { status: controller.signal.aborted ? 'timeout' : 'unavailable' };
    } finally {
      clearTimeout(timer);
      context.signal?.removeEventListener('abort', abortListener);
    }
    if (response.ok) return { status: 'success', body };
    if (response.status === 404) return { status: 'not_found' };
    if (response.status === 401 || response.status === 403) return { status: 'unauthorized' };
    if (response.status === 429 && credentialFallback
      && /daily[ _-]?budget|budget[ _-]?(?:exceeded|exhausted)|quota[ _-]?(?:exceeded|exhausted)|credits?[ _-]?(?:exceeded|exhausted)/i.test(body)) {
      return { status: 'rate_limited', allowFallback: true };
    }
    if (response.status === 429 || response.status >= 500) {
      const delay = retryAfter(response);
      coolDown(url, context, delay);
      if (attempt + 1 < maxAttempts && delay <= 1500 && delay < context.deadline - Date.now()) { await wait(delay, context.signal); continue; }
    }
    return { status: response.status === 429 ? 'rate_limited' : 'unavailable' };
  }
  return { status: 'unavailable' };
}
function comparison(entry, record) {
  const title = Boolean(entry.title && titleKey(entry.title) === titleKey(record.title)) || strongTitle(entry.title, record.title);
  const authors = authorMatch(entry.authors, record.authors);
  const year = entry.year && record.year ? Math.abs(entry.year - record.year) <= 1 : null;
  const exactDoi = Boolean(entry.doi && record.doi === entry.doi);
  const exactArxiv = Boolean(entry.arxiv_id && record.arxiv_id === entry.arxiv_id);
  const arxivDoiAlias = Boolean(record.arxiv_id && arxivFromDoi(entry.doi) === record.arxiv_id);
  const crossLanguage = (!title && hanLatinDifference(entry.title, record.title))
    || (authors === false && hanLatinDifference(entry.authors[0], record.authors[0]));
  return { title, authors, year, arxivDoiAlias, crossLanguage, exact: exactDoi || exactArxiv || arxivDoiAlias, strong: title && authors === true && year === true };
}
async function lookup(provider, kind, identifier, context) {
  let url;
  if (provider === 'openalex') {
    url = new URL(kind === 'doi' ? `https://api.openalex.org/works/https://doi.org/${encodeURIComponent(identifier)}` : 'https://api.openalex.org/works');
    if (kind === 'title') { url.searchParams.set('search', identifier); url.searchParams.set('per-page', '5'); }
  } else if (provider === 'crossref') {
    url = new URL(kind === 'doi' ? `https://api.crossref.org/works/${encodeURIComponent(identifier)}` : 'https://api.crossref.org/works');
    if (kind === 'title') { url.searchParams.set('query.bibliographic', identifier); url.searchParams.set('rows', '5'); }
  } else {
    url = new URL('https://export.arxiv.org/api/query'); url.searchParams.set('id_list', identifier);
  }
  const publicUrl = url.toString();
  const keys = provider === 'openalex' ? context.keys : [null];
  let result;
  for (let i = 0; i < keys.length; i++) {
    if (keys[i]) url.searchParams.set('api_key', keys[i]);
    result = await request(url, context, { credentialFallback: provider === 'openalex' });
    if (result.status !== 'unauthorized' && !result.allowFallback) break;
  }
  if (result.status === 'not_found') return { source: { provider, url: publicUrl, status: 'not_found' }, records: [], success: true, kind };
  if (result.status !== 'success') return { source: { provider, url: publicUrl, status: result.status }, records: [], success: false, kind };
  try {
    let records;
    if (provider === 'arxiv') records = parseArxiv(result.body);
    else {
      const payload = JSON.parse(result.body);
      const raw = provider === 'openalex' ? (kind === 'doi' ? [payload] : payload.results)
        : kind === 'doi' ? [payload.message] : payload.message?.items;
      if (!Array.isArray(raw)) throw new Error('invalid_payload');
      const convert = provider === 'openalex' ? openalexRecord : crossrefRecord;
      records = raw.slice(0, 5).map(convert);
      if (records.some(r => !r)) throw new Error('invalid_payload');
    }
    records = records.map(r => sanitizeRecord(r, context.secrets));
    return { source: { provider, url: publicUrl, status: records.length ? 'success' : 'not_found' }, records, success: true, kind };
  } catch {
    return { source: { provider, url: publicUrl, status: 'unavailable' }, records: [], success: false, kind };
  }
}
async function catalog(provider, entry, context) {
  const results = [];
  if (entry.doi) {
    const direct = await lookup(provider, 'doi', entry.doi, context); results.push(direct);
    const record = direct.records.find(r => r.doi === entry.doi);
    if (record?.related_doi && record.related_doi !== entry.doi) {
      results.push(await lookup(provider, 'doi', record.related_doi, context));
    }
    if (record && (entry.extraction_confidence !== 'high' || comparison(entry, record).strong)) return results;
    // An unavailable provider is not asked again using a title; unrelated catalogs still run.
    if (!direct.success) return results;
  }
  if (entry.title.length >= 12) results.push(await lookup(provider, 'title', entry.title, context));
  return results;
}
async function scholar(entry, context, key) {
  const publicUrl = new URL('https://scholar.google.com/scholar'); publicUrl.searchParams.set('q', entry.title);
  const url = new URL('https://serpapi.com/search.json');
  url.searchParams.set('engine', 'google_scholar'); url.searchParams.set('q', entry.title); url.searchParams.set('api_key', key);
  // Paid personal requests are never retried or sent with another account's key.
  const result = await request(url, context, { credentialFallback: true, maxAttempts: 1 });
  const source = { provider: 'serpapi', url: publicUrl.toString(), status: result.status };
  if (result.status !== 'success') return { source, success: false, records: [], kind: 'title' };
  try {
    const payload = JSON.parse(result.body);
    if (payload.error || !Array.isArray(payload.organic_results)) throw new Error('invalid_payload');
    const records = payload.organic_results.slice(0, 5).map(item => {
      const title = clean(item.title);
      if (!title) return null;
      const publication = item.publication_info || {};
      const authors = Array.isArray(publication.authors) ? publication.authors.map(a => clean(a.name, 150)).filter(Boolean)
        : clean(publication.summary).split(/\s[-–]\s/)[0].split(/[,;&]/).map(a => clean(a, 150)).filter(Boolean);
      const years = clean(publication.summary).match(/\b(?:1[5-9]\d{2}|20\d{2}|21\d{2})\b/g) || [];
      let doi = null, arxiv_id = null;
      try {
        const link = new URL(item.link);
        if (link.protocol === 'https:' && !link.username && !link.password) {
          if (['doi.org', 'dx.doi.org'].includes(link.hostname)) doi = normalizeDoi(link.toString());
          if (['arxiv.org', 'export.arxiv.org'].includes(link.hostname)) arxiv_id = normalizeArxiv(link.toString());
        }
      } catch { /* Public source stays the fixed Scholar search URL. */ }
      return sanitizeRecord({ title, authors, year: yearValue(Number(years.at(-1))), doi, arxiv_id,
        provider: 'serpapi', type: arxiv_id ? 'preprint' : 'article', related_doi: null,
        url: doi ? doiUrl(doi) : arxiv_id ? arxivUrl(arxiv_id) : publicUrl.toString() }, context.secrets);
    }).filter(Boolean);
    source.status = records.length ? 'success' : 'not_found';
    return { source, success: true, records, kind: 'title' };
  } catch { source.status = 'unavailable'; return { source, success: false, records: [], kind: 'title' }; }
}
function redactResult(value, secrets) {
  if (typeof value === 'string') {
    return secrets.reduce((text, secret) => {
      const variants = new Set([secret, encodeURIComponent(secret), new URLSearchParams({ q: secret }).toString().slice(2)]);
      for (const variant of variants) text = text.split(variant).join('[redacted]');
      return text;
    }, value);
  }
  if (Array.isArray(value)) return value.map(v => redactResult(v, secrets));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, redactResult(v, secrets)]));
  return value;
}
function comparisons(entry, record, equivalent = false) {
  if (!record) return [];
  const c = comparison(entry, record);
  return [
    { field: 'title', cited: entry.title || null, matched: record.title, status: !entry.title ? 'missing' : c.title ? 'match' : c.crossLanguage ? 'unknown' : 'different' },
    { field: 'authors', cited: entry.authors, matched: record.authors, status: !entry.authors.length ? 'missing' : c.authors === null ? 'unknown' : c.authors ? 'match' : c.crossLanguage ? 'unknown' : 'different' },
    { field: 'year', cited: entry.year, matched: record.year, status: !entry.year ? 'missing' : !record.year ? 'unknown' : c.year ? 'match' : equivalent ? 'equivalent' : 'different' },
    { field: 'doi', cited: entry.doi, matched: record.doi || (c.arxivDoiAlias ? arxivUrl(record.arxiv_id) : null),
      status: c.arxivDoiAlias ? 'equivalent' : !entry.doi ? (record.doi ? 'missing' : 'unknown') : !record.doi ? 'unknown' : entry.doi === record.doi ? 'match' : equivalent ? 'equivalent' : 'different' },
    ...(entry.arxiv_id || record.arxiv_id ? [{ field: 'arxiv_id', cited: entry.arxiv_id, matched: record.arxiv_id,
      status: !entry.arxiv_id ? 'missing' : !record.arxiv_id ? 'unknown' : entry.arxiv_id === record.arxiv_id ? 'match' : 'different' }] : []),
  ];
}
function decide(entry, lookups) {
  const records = lookups.flatMap(r => r.records);
  const attempted = [...new Set(lookups.map(r => r.source.provider))];
  const succeeded = attempted.filter(p => lookups.filter(r => r.source.provider === p).every(r => r.success));
  const coverage = { providers_attempted: attempted, providers_succeeded: succeeded,
    providers_unavailable: attempted.filter(p => !succeeded.includes(p)), complete: lookups.length > 0 && lookups.every(r => r.success),
    extraction: entry.extraction_confidence, advisory: false };
  let category = 'unverified', reason_code = 'insufficient_evidence', matched = null, equivalent = false;
  const exacts = records.filter(r => comparison(entry, r).exact);
  const fullMetadata = Boolean(entry.title && entry.authors.length && entry.year && entry.extraction_confidence === 'high');
  const strong = records.filter(r => comparison(entry, r).strong);
  const preprint = exacts.find(r => r.provider === 'arxiv') || exacts.find(r => ['preprint', 'posted-content'].includes(r.type) && r.related_doi);
  const publication = preprint?.related_doi && records.find(r => r.doi === preprint.related_doi && strongTitle(preprint.title, r.title)
    && authorMatch(preprint.authors, r.authors) === true && !['preprint', 'posted-content'].includes(r.type));

  if (publication && entry.doi === publication.doi && comparison(entry, publication).strong) {
    // The citation names the published edition. Its linked preprint establishes
    // identifier equivalence, while the cited DOI supplies the publication year.
    category = 'verified'; reason_code = 'identifier_verified'; matched = publication; equivalent = true;
  } else if (preprint && publication && comparison(entry, preprint).strong
    && (!entry.doi || entry.doi === preprint.doi || arxivFromDoi(entry.doi) === preprint.arxiv_id)) {
    category = 'upgrade'; reason_code = 'publication_available'; matched = publication; equivalent = true;
  } else if (exacts.length) {
    // Prefer the exact preprint record over a later publication's year or title variants.
    matched = preprint || exacts.find(r => comparison(entry, r).strong) || exacts[0];
    const c = comparison(entry, matched);
    if (c.crossLanguage) { category = 'unverified'; reason_code = 'cross_language_metadata'; }
    else if (!fullMetadata) { category = 'verified'; reason_code = 'identifier_verified'; }
    else if (c.strong) { category = 'verified'; reason_code = 'identifier_verified'; }
    else {
      const corrected = strong.find(r => r.doi && entry.doi && r.doi !== entry.doi);
      if (corrected && !preprint) { matched = corrected; category = 'mismatch'; reason_code = 'identifier_conflict'; }
      else if (!c.title || c.authors === false || c.year === false) { category = 'mismatch'; reason_code = 'metadata_conflict'; }
      else { category = 'unverified'; reason_code = 'incomplete_catalog_metadata'; }
    }
  } else if (strong.length && fullMetadata) {
    matched = strong[0];
    if ((entry.has_doi && matched.doi !== entry.doi) || (entry.has_arxiv && matched.arxiv_id && matched.arxiv_id !== entry.arxiv_id)) {
      category = 'mismatch'; reason_code = 'identifier_conflict';
    } else if (entry.has_arxiv && !matched.arxiv_id) { category = 'unverified'; reason_code = 'identifier_unresolved'; }
    else if (!entry.doi && matched.doi && !entry.arxiv_id) { category = 'incomplete'; reason_code = 'missing_doi'; }
    else { category = 'verified'; reason_code = 'metadata_verified'; }
  } else if (!fullMetadata) reason_code = 'incomplete_extraction';
  else if (!coverage.complete) reason_code = 'provider_unavailable';
  else {
    const meaningfulEnglishArticle = ['J', 'C', 'ARTICLE', 'JOURNAL-ARTICLE', 'PROCEEDINGS-ARTICLE'].includes(entry.type_code)
      && /^[\x00-\x7f\u00a0-\u024f\u2000-\u206f]+$/.test(entry.title)
      && titleKey(entry.title).split(' ').length >= 4 && entry.title.length >= 24;
    const emptySearches = ['openalex', 'crossref'].every(p => lookups.some(r => r.source.provider === p && r.kind === 'title' && r.success && r.records.length === 0));
    if (meaningfulEnglishArticle && emptySearches && records.length === 0) {
      category = 'suspected'; reason_code = 'not_found_in_checked_databases'; coverage.advisory = true;
    } else reason_code = records.length ? 'ambiguous_catalog_candidates' : 'outside_database_coverage';
  }
  if (['verified', 'incomplete'].includes(category) && entry.arxiv_id && !records.some(r => r.arxiv_id === entry.arxiv_id)
    && lookups.some(r => r.source.provider === 'arxiv' && r.source.status === 'not_found')) {
    category = 'unverified'; reason_code = 'identifier_unresolved';
  }
  const fieldComparisons = comparisons(entry, matched, equivalent);
  if (entry.extraction_confidence !== 'high') fieldComparisons.forEach(c => { if (c.status === 'different') c.status = 'unknown'; });
  return { category, reason_code, matched, comparisons: fieldComparisons, sources: lookups.map(r => r.source), coverage };
}

/** Bounded, database-only reference verification. Cancellation rejects with a safe AbortError. */
async function verifyReference(input, options = {}) {
  checkAbort(options.signal);
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== 'function') throw new TypeError('A fetch implementation is required');
  const entry = normalizeEntry(input);
  // This private flag is supplied only by persisted local-account policy in
  // referencePersonalAccess. HTTP inputs never become provider options.
  const credentials = personalReferenceCredentials(options, options.allowSharedQuota === true);
  const { personalKey, serpapiKey, allowSharedQuota } = credentials;
  const openalexKeys = [...new Set([personalKey, ...(credentials.platformKeys || [])].filter(Boolean))].slice(0, 4);
  const openalexEnabled = Boolean(personalKey || allowSharedQuota);
  const secrets = [...new Set([...openalexKeys, ...(serpapiKey ? [serpapiKey] : [])])];
  const keys = openalexKeys.length ? openalexKeys : allowSharedQuota ? [null] : [];
  const context = { fetchImpl, signal: options.signal, secrets, keys, deadline: Date.now() + TOTAL_TIMEOUT_MS };
  // Preserve provider roles and ordered platform fallback in the private hash:
  // identical token bytes across providers do not imply the same access scope.
  const credentialIdentity = { personal_openalex: personalKey, platform_openalex: credentials.platformKeys || [],
    personal_serpapi: serpapiKey, shared_quota: Boolean(allowSharedQuota) };
  const cacheKey = createHash('sha256').update(JSON.stringify([entry, credentialIdentity])).digest('hex');
  let cache = caches.get(fetchImpl);
  if (!cache) { cache = new Map(); caches.set(fetchImpl, cache); }
  const cached = cache.get(cacheKey);
  if (cached && cached.expires > Date.now()) return structuredClone(cached.value);
  cache.delete(cacheKey);
  const results = await Promise.all([
    openalexEnabled ? catalog('openalex', entry, context) : [], catalog('crossref', entry, context),
    entry.arxiv_id ? lookup('arxiv', 'arxiv', entry.arxiv_id, context).then(r => [r]) : [],
    !openalexEnabled && serpapiKey && entry.title.length >= 12 ? scholar(entry, context, serpapiKey).then(r => [r]) : [],
  ]);
  checkAbort(options.signal);
  const lookups = results.flat();
  let value = decide(entry, lookups);
  if (openalexEnabled && serpapiKey && ['unverified', 'suspected'].includes(value.category) && entry.title.length >= 12) {
    lookups.push(await scholar(entry, context, serpapiKey));
    checkAbort(options.signal);
    value = decide(entry, lookups);
    if (['suspected', 'unverified'].includes(value.category)) {
      value.category = 'unverified'; value.reason_code = 'supplemental_search_unresolved'; value.coverage.advisory = false;
    }
  }
  value = redactResult(value, secrets);
  // Failures never poison later retries or accounts. A successful cache is bounded and detached.
  if (value.coverage.complete) {
    for (const [key, result] of cache) if (result.expires <= Date.now()) cache.delete(key);
    while (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value);
    cache.set(cacheKey, { expires: Date.now() + CACHE_TTL_MS, value: structuredClone(value) });
  }
  return value;
}

module.exports = { verifyReference };
