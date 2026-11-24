import { describe, it, expect, vi, afterEach } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { verifyReference } = require('../src/normative/referenceVerificationCore');

const title = 'Reliable metadata verification for scholarly references';
const entry = (extra = {}) => ({ id: 'ref-1', text: 'Smith J. Reliable metadata verification for scholarly references. 2023.',
  title, authors: ['Smith, J.'], year: 2023, doi: null, arxiv_id: null, type_code: 'J',
  extraction_confidence: 'high', location: { page_number: 4 }, ...extra });
const oa = (extra = {}) => ({ id: 'https://openalex.org/W123', title, publication_year: 2023,
  doi: 'https://doi.org/10.1234/reliable', type: 'article',
  authorships: [{ author: { display_name: 'John Smith' } }], ...extra });
const cr = (extra = {}) => ({ DOI: '10.1234/reliable', title: [title], type: 'journal-article',
  author: [{ given: 'John', family: 'Smith' }], published: { 'date-parts': [[2023, 1, 1]] }, ...extra });
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), { status, headers });
const xml = (extra = '') => new Response(`<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>
  <id>http://arxiv.org/abs/2301.01234v2</id><title>${title}</title><author><name>John Smith</name></author>
  <published>2023-01-10T00:00:00Z</published>${extra}</entry></feed>`, { headers: { 'content-type': 'application/atom+xml' } });
function fixture({ openalex = [], crossref = [], arxiv, handler } = {}) {
  const requests = [];
  const fetchImpl = async (input, init) => {
    const url = new URL(input); requests.push({ url, init });
    const special = handler?.(url, init, requests.length);
    if (special !== undefined) return special;
    if (url.hostname === 'api.openalex.org') {
      if (url.pathname !== '/works') return openalex.length ? json(openalex[0]) : json({}, 404);
      return json({ meta: { count: openalex.length }, results: openalex });
    }
    if (url.hostname === 'api.crossref.org') {
      if (url.pathname !== '/works') return crossref.length ? json({ status: 'ok', message: crossref[0] }) : json({}, 404);
      return json({ status: 'ok', message: { items: crossref } });
    }
    if (url.hostname === 'export.arxiv.org') return arxiv ? arxiv() : new Response('<feed xmlns="http://www.w3.org/2005/Atom"></feed>');
    if (url.hostname === 'api.datacite.org') return url.pathname === '/dois' ? json({ data: [] }) : json({}, 404);
    throw new Error('Unexpected outbound destination');
  };
  return { fetchImpl, requests, personalKey: 'fixture-personal-openalex', crossrefScheduler: require('../src/normative/referenceVerificationCore').createCrossrefScheduler() };
}
afterEach(() => vi.useRealTimers());

describe('database reference verification', () => {
  it('matches canonical DOI and preserves caller input', async () => {
    const f = fixture({ openalex: [oa()], crossref: [cr()] });
    const cited = entry({ doi: 'https://DX.doi.org/10.1234/RELIABLE.' });
    const before = structuredClone(cited);
    const value = await verifyReference(cited, f);
    expect(value.category).toBe('verified');
    expect(value.matched.doi).toBe('10.1234/reliable');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'doi', status: 'match' }));
    expect(cited).toEqual(before);
    expect(f.requests.every(r => r.init.redirect === 'error')).toBe(true);
  });

  it('matches title typography and surname/initial variants with corroborating year', async () => {
    const f = fixture({ openalex: [oa({ title: 'Reliable metadata verification: for scholarly references' })] });
    const value = await verifyReference(entry({ authors: ['J. SMITH'] }), f);
    expect(value.category).toBe('incomplete');
    expect(value.reason_code).toBe('missing_doi');
    expect(value.matched.title).toContain('Reliable metadata');
  });

  it('recognizes bibliography surname-first names without a comma', async () => {
    expect((await verifyReference(entry({ authors: ['SMITH J'] }), fixture({ crossref: [cr()] }))).category).toBe('incomplete');
  });

  it.each([
    ['van der Waals, J.', 'Johannes van der Waals'],
    ['GARCIA MARQUEZ G M', 'Gabriel Garcia Marquez'],
    ['Smith John', 'John Smith'],
  ])('accepts author-name ordering and compound surnames: %s', async (cited, indexed) => {
    const value = await verifyReference(entry({ authors: [cited], doi: '10.1234/reliable' }), fixture({ openalex: [oa({ authorships: [{ author: { display_name: indexed } }] })] }));
    expect(value.category).toBe('verified');
  });

  it('does not accept similar titles without author corroboration', async () => {
    const value = await verifyReference(entry(), fixture({ openalex: [oa({ authorships: [{ author: { display_name: 'Jane Brown' } }] })] }));
    expect(value.category).toBe('unverified');
  });

  it('explains a wrong DOI even when title lookup finds the cited work', async () => {
    const f = fixture({ openalex: [oa()], crossref: [cr()], handler: url => {
      if (url.pathname.includes('10.9999')) return url.hostname === 'api.openalex.org'
        ? json(oa({ title: 'Unrelated geological measurements', doi: 'https://doi.org/10.9999/wrong' }))
        : json({ message: cr({ DOI: '10.9999/wrong', title: ['Unrelated geological measurements'] }) });
    } });
    const value = await verifyReference(entry({ doi: '10.9999/wrong' }), f);
    expect(value.category).toBe('mismatch');
    expect(value.reason_code).toBe('identifier_conflict');
    expect(value.matched.doi).toBe('10.1234/reliable');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'doi', status: 'different' }));
  });

  it('reports a clear author conflict on the exact DOI', async () => {
    const f = fixture({ crossref: [cr({ author: [{ given: 'Jane', family: 'Brown' }] })] });
    const value = await verifyReference(entry({ doi: '10.1234/reliable' }), f);
    expect(value.category).toBe('mismatch');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'authors', status: 'different' }));
  });

  it('abstains on translated Han/Latin metadata for an exact DOI', async () => {
    const value = await verifyReference(entry({ doi: '10.1234/reliable', title: '学术参考文献的可靠元数据核验方法', authors: ['史密斯'] }), fixture({ crossref: [cr()] }));
    expect(value.category).toBe('unverified');
    expect(value.reason_code).toBe('cross_language_metadata');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'title', status: 'unknown' }));
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'authors', status: 'unknown' }));
  });

  it('preserves a clear same-script title conflict for an exact DOI', async () => {
    const value = await verifyReference(entry({ doi: '10.1234/reliable', title: 'A completely different geological measurement study' }), fixture({ crossref: [cr()] }));
    expect(value.category).toBe('mismatch');
    expect(value.reason_code).toBe('metadata_conflict');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'title', status: 'different' }));
  });

  it('verifies matching native Han metadata on an exact DOI', async () => {
    const citedTitle = '学术参考文献的可靠元数据核验方法';
    const value = await verifyReference(entry({ doi: '10.1234/reliable', title: citedTitle, authors: ['张三'] }), fixture({
      crossref: [cr({ title: [citedTitle], author: [{ name: '张三' }] })],
    }));
    expect(value.category).toBe('verified');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'title', status: 'match' }));
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'authors', status: 'match' }));
  });

  it('does not let a matching coauthor hide a wrong first cited author', async () => {
    const f = fixture({ crossref: [cr({ author: [{ given: 'John', family: 'Smith' }, { given: 'Mary', family: 'Jones' }] })] });
    const value = await verifyReference(entry({ doi: '10.1234/reliable', authors: ['Fraud Person', 'John Smith'] }), f);
    expect(value.category).toBe('mismatch');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'authors', status: 'different' }));
  });

  it('does not verify an explicit unfound arXiv identifier from an unrelated title-only identifier', async () => {
    const value = await verifyReference(entry({ arxiv_id: '2401.99999' }), fixture({ crossref: [cr()] }));
    expect(value.category).toBe('unverified');
    expect(value.reason_code).toBe('identifier_unresolved');
  });

  it('accepts a one-year online/print publication variation', async () => {
    const value = await verifyReference(entry({ doi: '10.1234/reliable', year: 2022 }), fixture({ crossref: [cr()] }));
    expect(value.category).toBe('verified');
  });

  it('accepts short exact titles when an authoritative DOI identifies the work', async () => {
    const value = await verifyReference(entry({ title: 'Metadata', doi: '10.1234/reliable' }), fixture({ crossref: [cr({ title: ['Metadata'] })] }));
    expect(value.category).toBe('verified');
  });

  it('uses explicit Crossref preprint/publication relations without inventing an identifier conflict', async () => {
    const f = fixture({ handler: url => {
      if (url.hostname !== 'api.crossref.org') return undefined;
      if (url.pathname.includes('10.1234%2Fpreprint')) return json({ message: cr({ DOI: '10.1234/preprint', type: 'posted-content',
        relation: { 'is-preprint-of': [{ 'id-type': 'doi', id: '10.1234/reliable' }] } }) });
      return undefined;
    }, crossref: [cr({ published: { 'date-parts': [[2025]] } })] });
    const value = await verifyReference(entry({ doi: '10.1234/preprint', type_code: 'EB' }), f);
    expect(value.category).toBe('upgrade');
    expect(value.matched.doi).toBe('10.1234/reliable');
  });

  it('uses exact arXiv metadata with canonical versionless identifiers', async () => {
    const f = fixture({ arxiv: () => xml() });
    const value = await verifyReference(entry({ arxiv_id: 'https://arxiv.org/abs/2301.01234v3', type_code: 'EB' }), f);
    expect(value.category).toBe('verified');
    expect(value.matched.arxiv_id).toBe('2301.01234');
    expect(f.requests.some(r => r.url.searchParams.get('id_list') === '2301.01234')).toBe(true);
  });

  it('offers a publication upgrade only when arXiv relation and publication metadata corroborate it', async () => {
    const f = fixture({ openalex: [oa({ publication_year: 2025 })], crossref: [cr({ published: { 'date-parts': [[2025]] } })],
      arxiv: () => xml('<arxiv:doi>10.1234/reliable</arxiv:doi>') });
    const value = await verifyReference(entry({ arxiv_id: '2301.01234', type_code: 'EB' }), f);
    expect(value.category).toBe('upgrade');
    expect(value.matched.doi).toBe('10.1234/reliable');
  });

  it.each(['2301.01234', null])('recognizes an arXiv DOI as the preprint identifier with arxiv_id=%s', async arxiv_id => {
    const f = fixture({ openalex: [oa({ publication_year: 2025 })], crossref: [cr({ published: { 'date-parts': [[2025]] } })],
      arxiv: () => xml('<arxiv:doi>10.1234/reliable</arxiv:doi>'),
      handler: url => url.pathname.includes('10.48550') ? json({}, 404) : undefined });
    const value = await verifyReference(entry({ doi: 'https://doi.org/10.48550/arXiv.2301.01234', arxiv_id, type_code: 'EB' }), f);
    expect(value.category).toBe('upgrade');
    expect(value.reason_code).toBe('publication_available');
    expect(value.matched.doi).toBe('10.1234/reliable');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'doi', status: 'equivalent' }));
    expect(f.requests.some(r => r.url.hostname === 'export.arxiv.org' && r.url.searchParams.get('id_list') === '2301.01234')).toBe(true);
  });

  it('verifies the arXiv DOI alias without inferring a publication relation', async () => {
    const f = fixture({ arxiv: () => xml() });
    const value = await verifyReference(entry({ doi: '10.48550/arxiv.2301.01234', arxiv_id: '2301.01234', type_code: 'EB' }), f);
    expect(value.category).toBe('verified');
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'doi', status: 'equivalent' }));
  });

  it('compares a cited publication DOI against its edition when a related preprint is also cited', async () => {
    const f = fixture({ crossref: [cr({ published: { 'date-parts': [[2025]] } })],
      arxiv: () => xml('<arxiv:doi>10.1234/reliable</arxiv:doi>') });
    const value = await verifyReference(entry({ doi: '10.1234/reliable', arxiv_id: '2301.01234', year: 2025 }), f);
    expect(value.category).toBe('verified');
    expect(value.matched.doi).toBe('10.1234/reliable');
    expect(value.matched.year).toBe(2025);
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'year', matched: 2025, status: 'match' }));
    expect(value.comparisons).toContainEqual(expect.objectContaining({ field: 'doi', status: 'match' }));
    expect(value.comparisons.every(c => c.status !== 'different')).toBe(true);
  });

  it('does not invent a publication relation from a matching title alone', async () => {
    const f = fixture({ openalex: [oa()], arxiv: () => xml() });
    const value = await verifyReference(entry({ arxiv_id: '2301.01234', type_code: 'EB' }), f);
    expect(value.category).toBe('verified');
    expect(value.reason_code).not.toBe('publication_available');
  });

  it('requires high extraction and successful empty searches for an advisory suspicion', async () => {
    const value = await verifyReference(entry(), fixture());
    expect(value.category).toBe('suspected');
    expect(value.reason_code).toBe('not_found_in_checked_databases');
    expect(value.coverage).toMatchObject({ complete: true, advisory: true, providers_succeeded: ['openalex', 'crossref', 'datacite'] });
  });

  it.each([
    { extraction_confidence: 'partial' }, { title: '' }, { authors: [] }, { year: null },
    { title: '中文学位论文的数据核查方法' }, { type_code: 'D' }, { type_code: 'M' }, { type_code: 'EB' },
  ])('keeps incomplete or uncovered metadata unverified: %j', async extra => {
    expect((await verifyReference(entry(extra), fixture())).category).toBe('unverified');
  });

  it('can verify exact identifier existence despite partial extraction without an uncertain mismatch', async () => {
    const value = await verifyReference(entry({ doi: '10.1234/reliable', extraction_confidence: 'partial', title: 'Unreliable extraction', authors: [] }), fixture({ crossref: [cr()] }));
    expect(value.category).toBe('verified');
    expect(value.reason_code).toBe('identifier_verified');
  });

  it('keeps a provider outage unverified instead of interpreting it as no matching work', async () => {
    const f = fixture({ handler: url => url.hostname === 'api.openalex.org' ? json({ error: 'unavailable' }, 503) : undefined });
    const value = await verifyReference(entry(), f);
    expect(value.category).toBe('unverified');
    expect(value.coverage.complete).toBe(false);
    expect(value.sources.some(s => s.provider === 'openalex' && s.status === 'unavailable')).toBe(true);
  });

  it('preserves authoritative matches when an unrelated provider is down', async () => {
    const f = fixture({ crossref: [cr()], handler: url => url.hostname === 'api.openalex.org' ? json({}, 403) : undefined });
    const value = await verifyReference(entry({ doi: '10.1234/reliable' }), f);
    expect(value.category).toBe('verified');
    expect(value.coverage.complete).toBe(false);
  });

  it('never falls back to platform credentials after a personal budget failure', async () => {
    const f = fixture({ openalex: [oa()], handler: url => {
      if (url.hostname !== 'api.openalex.org') return undefined;
      if (url.searchParams.get('api_key') === 'private-secret-key') return json({ error: 'daily_budget_exceeded private-secret-key' }, 429, { 'retry-after': '3600' });
      if (url.searchParams.get('api_key') === 'platform-key-one') return json({}, 401);
    } });
    const value = await verifyReference(entry(), { ...f, personalKey: 'private-secret-key', platformKeys: ['platform-key-one', 'platform-key-two'] });
    expect(value.category).toBe('unverified');
    expect(f.requests.filter(r => r.url.hostname === 'api.openalex.org').map(r => r.url.searchParams.get('api_key')))
      .toEqual(['private-secret-key']);
    expect(JSON.stringify(value)).not.toMatch(/private-secret-key|platform-key|api_key/);
    expect(value.coverage.complete).toBe(false);
  });

  it('does not let one account failure poison another account cache or return mutable cached objects', async () => {
    const f = fixture({ handler: url => {
      if (url.hostname === 'api.openalex.org' && url.searchParams.get('api_key') === 'blocked-account') return json({}, 403);
      if (url.hostname === 'api.openalex.org') return json({ results: [oa()] });
    } });
    const a = await verifyReference(entry(), { ...f, personalKey: 'blocked-account' });
    const b = await verifyReference(entry(), { ...f, personalKey: 'working-account' });
    expect(a.category).toBe('unverified'); expect(b.category).toBe('incomplete');
    b.matched.title = 'mutated';
    const count = f.requests.length;
    const c = await verifyReference(entry(), { ...f, personalKey: 'working-account' });
    expect(c.matched.title).toBe(title); expect(f.requests).toHaveLength(count);
  });

  it('isolates a local shared-quota cache from an ordinary SerpAPI-only account using the same token', async () => {
    const f = fixture({ openalex: [oa()], handler: url => url.hostname === 'serpapi.com' ? json({ organic_results: [{ title,
      link: 'https://doi.org/10.1234/reliable', publication_info: { summary: 'John Smith - Journal, 2023', authors: [{ name: 'John Smith' }] } }] }) : undefined });
    await verifyReference(entry(), { fetchImpl: f.fetchImpl, serpapiKey: 'same-owned-serp-key', allowSharedQuota: true });
    const ordinary = await verifyReference(entry(), { fetchImpl: f.fetchImpl, serpapiKey: 'same-owned-serp-key' });
    expect(ordinary.sources.some(source => source.provider === 'openalex')).toBe(false);
    expect(f.requests.filter(row => row.url.hostname === 'serpapi.com')).toHaveLength(1);
  });

  it('isolates OpenAlex and SerpAPI credentials with identical token bytes in the cache identity', async () => {
    const f = fixture({ openalex: [oa()], handler: url => url.hostname === 'serpapi.com' ? json({ organic_results: [{ title,
      link: 'https://doi.org/10.1234/reliable', publication_info: { summary: 'John Smith - Journal, 2023', authors: [{ name: 'John Smith' }] } }] }) : undefined });
    await verifyReference(entry(), { fetchImpl: f.fetchImpl, personalKey: 'identical-provider-token' });
    const serpapiOnly = await verifyReference(entry(), { fetchImpl: f.fetchImpl, serpapiKey: 'identical-provider-token' });
    expect(serpapiOnly.sources.some(source => source.provider === 'openalex')).toBe(false);
    expect(serpapiOnly.sources.some(source => source.provider === 'serpapi' && source.status === 'success')).toBe(true);
    expect(f.requests.filter(row => row.url.hostname === 'serpapi.com')).toHaveLength(1);
  });

  it('bounds a long Retry-After instead of retrying before the server allows it', async () => {
    const f = fixture({ handler: url => url.hostname === 'api.crossref.org' ? json({}, 429, { 'retry-after': '120' }) : undefined });
    const value = await verifyReference(entry(), f);
    expect(value.category).toBe('unverified');
    expect(f.requests.filter(r => r.url.hostname === 'api.crossref.org')).toHaveLength(1);
    expect(value.sources.some(s => s.status === 'rate_limited')).toBe(true);
  });

  it('does not rotate OpenAlex keys to bypass a per-second Retry-After', async () => {
    const f = fixture({ handler: url => url.hostname === 'api.openalex.org' ? json({ reason: 'requests_per_second' }, 429, { 'retry-after': '60' }) : undefined });
    const value = await verifyReference(entry(), { ...f, personalKey: 'personal-paced-key', platformKeys: ['platform-paced-key'] });
    expect(value.category).toBe('unverified');
    expect(f.requests.filter(r => r.url.hostname === 'api.openalex.org')).toHaveLength(1);
  });

  it('honors a provider Retry-After across different references sharing a transport', async () => {
    vi.useFakeTimers();
    const f = fixture({ handler: url => url.hostname === 'api.openalex.org' ? json({ reason: 'requests_per_second' }, 429, { 'retry-after': '60' }) : undefined });
    const first = verifyReference(entry(), f);
    const second = verifyReference(entry({ title: 'Another meaningful scholarly reference title' }), f);
    await vi.advanceTimersByTimeAsync(1000);
    expect((await first).category).toBe('unverified');
    expect((await second).category).toBe('unverified');
    expect(f.requests.filter(r => r.url.hostname === 'api.openalex.org')).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(60000);
    const third = verifyReference(entry({ title: 'A third meaningful scholarly reference title' }), f);
    await vi.advanceTimersByTimeAsync(0); await third;
    expect(f.requests.filter(r => r.url.hostname === 'api.openalex.org')).toHaveLength(2);
  });

  it('bounds hung fetch implementations even when they ignore the abort signal', async () => {
    vi.useFakeTimers();
    const f = fixture({ handler: url => url.hostname === 'api.openalex.org' ? new Promise(() => {}) : undefined });
    const pending = verifyReference(entry(), f);
    await vi.advanceTimersByTimeAsync(18000);
    const value = await pending;
    expect(value.category).toBe('unverified');
    expect(value.sources.some(s => s.status === 'timeout')).toBe(true);
    expect(f.requests.filter(r => r.url.hostname === 'api.openalex.org')).toHaveLength(2);
  });

  it('paces exact arXiv requests across references on the same transport', async () => {
    vi.useFakeTimers();
    const f = fixture({ arxiv: () => xml() });
    const first = verifyReference(entry({ arxiv_id: '2301.01234' }), f);
    await vi.advanceTimersByTimeAsync(0); await first;
    const second = verifyReference(entry({ arxiv_id: '2301.01235' }), f);
    await vi.advanceTimersByTimeAsync(2999);
    expect(f.requests.filter(r => r.url.hostname === 'export.arxiv.org')).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1); await second;
    expect(f.requests.filter(r => r.url.hostname === 'export.arxiv.org')).toHaveLength(2);
  });

  it('does not count a truncated Atom entry as an authoritative empty result', async () => {
    const value = await verifyReference(entry({ arxiv_id: '2301.01234' }), fixture({ arxiv: () => new Response('<feed><entry><id>http://arxiv.org/abs/2301.01234</id></feed>') }));
    expect(value.coverage.complete).toBe(false);
    expect(value.sources.find(s => s.provider === 'arxiv').status).toBe('unavailable');
  });

  it('honors short Retry-After pacing and bounds retries', async () => {
    vi.useFakeTimers();
    let crossrefCalls = 0;
    const f = fixture({ handler: url => {
      if (url.hostname === 'api.crossref.org' && ++crossrefCalls === 1) return json({}, 429, { 'retry-after': '1' });
    } });
    const pending = verifyReference(entry(), f);
    await vi.advanceTimersByTimeAsync(999);
    expect(crossrefCalls).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect((await pending).category).toBe('suspected');
    expect(crossrefCalls).toBe(2);
  });

  it('cancels an in-flight request promptly without publishing raw errors', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const f = fixture({ handler: (_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new Error('secret from a provider request')), { once: true });
    }) });
    const pending = verifyReference(entry(), { ...f, signal: controller.signal });
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('cancels before a scheduled request starts without waiting for its timeout', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const f = fixture({ handler: () => new Promise(() => {}) });
    const pending = verifyReference(entry(), { ...f, signal: controller.signal });
    let rejection;
    pending.catch(error => { rejection = error; });
    controller.abort();
    await vi.advanceTimersByTimeAsync(0);
    expect(rejection?.name).toBe('AbortError');
    expect(f.requests).toHaveLength(0);
  });

  it('rejects already-cancelled calls even with a cached match', async () => {
    const f = fixture({ crossref: [cr()] });
    await verifyReference(entry(), f);
    const controller = new AbortController(); controller.abort();
    await expect(verifyReference(entry(), { ...f, signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('treats malformed provider payloads and XML entities as unavailable', async () => {
    const f = fixture({ handler: url => url.hostname === 'api.openalex.org' ? json({ results: 'not-an-array' }) : undefined,
      arxiv: () => new Response('<!DOCTYPE feed [<!ENTITY x SYSTEM="file:///private">]><feed><entry><title>&x;</title></entry></feed>') });
    const value = await verifyReference(entry({ arxiv_id: '2301.01234' }), f);
    expect(value.category).toBe('unverified'); expect(value.coverage.complete).toBe(false);
    expect(JSON.stringify(value)).not.toContain('file:///');
  });

  it('does not trust arbitrary provider URLs or follow redirects', async () => {
    const f = fixture({ crossref: [cr({ URL: 'javascript:alert(1)' })],
      handler: url => url.hostname === 'api.openalex.org' ? new Response(null, { status: 302, headers: { location: 'http://127.0.0.1/private' } }) : undefined });
    const value = await verifyReference(entry({ doi: '10.1234/reliable' }), f);
    expect(value.category).toBe('verified');
    expect(value.matched.url).toBe('https://doi.org/10.1234/reliable');
    expect(JSON.stringify(value)).not.toMatch(/javascript:|127\.0\.0\.1/);
  });

  it('uses a personal supplemental Scholar key only after unresolved databases', async () => {
    const f = fixture({ handler: url => url.hostname === 'serpapi.com' ? json({ organic_results: [{ title,
      link: 'https://doi.org/10.1234/reliable', publication_info: { summary: 'J Smith - Journal of Metadata, 2023', authors: [{ name: 'J Smith' }] } }] }) : undefined });
    const value = await verifyReference(entry(), { ...f, serpapiKey: 'private-scholar-secret' });
    expect(value.category).toBe('incomplete');
    expect(value.sources).toContainEqual(expect.objectContaining({ provider: 'serpapi', status: 'success', url: expect.stringContaining('https://scholar.google.com/scholar?') }));
    expect(f.requests.find(r => r.url.hostname === 'serpapi.com').url.searchParams.get('api_key')).toBe('private-scholar-secret');
    expect(JSON.stringify(value)).not.toMatch(/private-scholar-secret|api_key/);
  });

  it('skips supplemental paid search when an indexed work already matches', async () => {
    const f = fixture({ crossref: [cr()] });
    const value = await verifyReference(entry(), { ...f, serpapiKey: 'unused-personal-key' });
    expect(value.category).toBe('incomplete');
    expect(f.requests.some(r => r.url.hostname === 'serpapi.com')).toBe(false);
  });

  it.each([200, 429, 503])('keeps a supplemental empty/error response unverified (%d)', async status => {
    const f = fixture({ handler: url => url.hostname === 'serpapi.com' ? json(status === 200 ? { organic_results: [] } : { error: 'private-scholar-secret' }, status) : undefined });
    const value = await verifyReference(entry(), { ...f, serpapiKey: 'private-scholar-secret' });
    expect(value.category).toBe('unverified');
    expect(value.reason_code).toBe('supplemental_search_unresolved');
    expect(value.coverage.advisory).toBe(false);
    expect(JSON.stringify(value)).not.toContain('private-scholar-secret');
    expect(f.requests.filter(r => r.url.hostname === 'serpapi.com')).toHaveLength(1);
  });

  it('does not trust Scholar title-only matches or arbitrary links', async () => {
    const f = fixture({ handler: url => url.hostname === 'serpapi.com' ? json({ organic_results: [{ title,
      link: 'javascript:alert(1)', publication_info: { summary: '2023' } }] }) : undefined });
    const value = await verifyReference(entry(), { ...f, serpapiKey: 'scholar-only-key' });
    expect(value.category).toBe('unverified');
    expect(JSON.stringify(value)).not.toContain('javascript:');
  });

  it('redacts secrets even if a provider echoes them into its title or citation URLs', async () => {
    const f = fixture({ crossref: [cr({ title: [`${title} private-ref-key`] })] });
    const value = await verifyReference(entry({ title: `${title} private-ref-key`, doi: '10.1234/reliable' }), { ...f, personalKey: 'private-ref-key' });
    expect(JSON.stringify(value)).not.toContain('private-ref-key');
  });
});
