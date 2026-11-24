import { createRequire } from 'node:module';
import { afterEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const { validateReferenceCredentials } = require('../src/auth/referenceCredentialValidation');
const openalexKey = 'candidate-openalex-token';
const serpapiKey = 'candidate-serpapi-token';
const openalexBody = { api_key: 'abc...xyz', rate_limit: { daily_budget_usd: 1, daily_used_usd: 1,
  daily_remaining_usd: 0, prepaid_balance_usd: 0, resets_at: '2026-11-26T00:00:00.000Z', resets_in_seconds: 3600 } };
const serpapiBody = { account_id: 'account-123', api_key: serpapiKey, account_email: 'test@example.test',
  account_status: 'Active', plan_id: 'free', plan_name: 'Free', plan_monthly_price: 0,
  plan_renewal_date: null, searches_per_month: 100, plan_searches_left: 0, extra_credits: 0,
  total_searches_left: 0, this_month_usage: 100, this_hour_searches: 0, last_hour_searches: 0,
  account_rate_limit_per_hour: 20 };
const cases = [
  { provider: 'openalex', field: 'api_key', key: openalexKey, body: openalexBody,
    endpoint: 'https://api.openalex.org/rate-limit', invalid: 'invalid_api_key', unavailable: 'openalex_verification_unavailable' },
  { provider: 'serpapi', field: 'serpapi_key', key: serpapiKey, body: serpapiBody,
    endpoint: 'https://serpapi.com/account.json', invalid: 'invalid_serpapi_key', unavailable: 'serpapi_verification_unavailable' },
];

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe.each(cases)('$provider personal credential verification', config => {
  const values = { [config.field]: config.key };
  const unavailable = { errorCode: config.unavailable, status: 503 };

  it('only sends the supplied token to the fixed free account endpoint and discards authenticated data', async () => {
    const candidate = 'encoded?key&with=reserved#characters';
    const fetchImpl = vi.fn(async (input, options) => {
      const url = new URL(input);
      expect(`${url.origin}${url.pathname}`).toBe(config.endpoint);
      expect([...url.searchParams.entries()]).toEqual([['api_key', candidate]]);
      expect(options).toMatchObject({ method: 'GET', redirect: 'error', headers: { Accept: 'application/json' } });
      expect(options.signal).toBeInstanceOf(AbortSignal);
      return Response.json({ ...config.body, api_key: config.provider === 'serpapi' ? candidate : 'abc...xyz' });
    });
    expect(await validateReferenceCredentials({ [config.field]: `  ${candidate}  ` }, { fetchImpl })).toBeUndefined();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it.each([401, 403])('treats HTTP%s as invalid without reading or reflecting its secret-bearing body', async status => {
    const response = Response.json({ error: 'private-provider-body' }, { status });
    const fetchImpl = async () => response;
    await expect(validateReferenceCredentials(values, { fetchImpl })).rejects.toMatchObject({ errorCode: config.invalid, status: 400 });
    expect(response.bodyUsed).toBe(false);
  });

  it.each([200, 400])('rejects a provider error in an HTTP%s body', async status => {
    const fetchImpl = async () => Response.json({ error: `Invalid API key: ${config.key}` }, { status });
    await expect(validateReferenceCredentials(values, { fetchImpl })).rejects.toMatchObject({ errorCode: config.invalid, status: 400 });
  });

  it.each([429, 500, 502, 503, 504, 302, 404, 204])('classifies HTTP%s as temporarily unverifiable', async status => {
    const fetchImpl = async () => new Response(null, { status });
    await expect(validateReferenceCredentials(values, { fetchImpl })).rejects.toMatchObject(unavailable);
  });

  it('discards network errors and their secret-bearing causes', async () => {
    const fetchImpl = async () => { throw new Error(`request failed ${config.key}`, { cause: new Error('private-transport-secret') }); };
    try {
      await validateReferenceCredentials(values, { fetchImpl });
      expect.fail('Verification should reject a failed provider request');
    } catch (error) {
      expect(error).toMatchObject(unavailable);
      expect(error.cause).toBeUndefined();
      expect(error.message).not.toContain(config.key);
      expect(error.stack).not.toContain('private-transport-secret');
    }
  });

  it.each([
    ['HTML', () => new Response('<html>provider temporarily unavailable</html>', { headers: { 'content-type': 'text/html' } })],
    ['malformed JSON', () => new Response('{bad-json-secret', { headers: { 'content-type': 'application/json' } })],
    ['empty object', () => Response.json({})],
    ['array', () => Response.json([])],
    ['null', () => Response.json(null)],
    ['missing authenticated identity', () => Response.json({ rate_limit: openalexBody.rate_limit, account_status: 'Active' })],
  ])('rejects %s as an unverified response', async (label, makeResponse) => {
    await expect(validateReferenceCredentials(values, { fetchImpl: async () => makeResponse() })).rejects.toMatchObject(unavailable);
  });

  it('rejects a redirected response even if it looks authenticated', async () => {
    const response = Response.json(config.body);
    Object.defineProperty(response, 'redirected', { value: true });
    await expect(validateReferenceCredentials(values, { fetchImpl: async () => response })).rejects.toMatchObject(unavailable);
  });

  it('bounds provider response bytes and cancels oversized streams', async () => {
    let cancelled = false;
    const response = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(' '.repeat(32769)));
      },
      cancel() { cancelled = true; },
    }), { headers: { 'content-type': 'application/json' } });
    await expect(validateReferenceCredentials(values, { fetchImpl: async () => response })).rejects.toMatchObject(unavailable);
    expect(cancelled).toBe(true);
  });

  it.each(['request', 'body'])('enforces its eight-second deadline while waiting for the %s', async stage => {
    vi.useFakeTimers();
    let signal;
    const fetchImpl = async (input, options) => {
      signal = options.signal;
      return stage === 'request' ? new Promise(() => {})
        : new Response(new ReadableStream({ start() {} }), { headers: { 'content-type': 'application/json' } });
    };
    const pending = validateReferenceCredentials(values, { fetchImpl });
    const result = expect(pending).rejects.toMatchObject(unavailable);
    await vi.advanceTimersByTimeAsync(8000);
    await result;
    expect(signal.aborted).toBe(true);
  });
});

describe('authenticated provider schemas and input preconditions', () => {
  it('accepts OpenAlex current dollar and legacy credit quota schemas even when quota is exhausted', async () => {
    for (const rate_limit of [openalexBody.rate_limit, { credits_limit: 100000, credits_used: 100000, credits_remaining: 0 }]) {
      await expect(validateReferenceCredentials({ api_key: openalexKey }, {
        fetchImpl: async () => Response.json({ api_key: 'abc...xyz', rate_limit }),
      })).resolves.toBeUndefined();
    }
  });

  it.each([{ daily_budget_usd: '1', daily_used_usd: 0, daily_remaining_usd: 1 }, {}, null])('rejects an invalid OpenAlex quota schema %j', async rate_limit => {
    await expect(validateReferenceCredentials({ api_key: openalexKey }, {
      fetchImpl: async () => Response.json({ api_key: 'abc...xyz', rate_limit }),
    })).rejects.toMatchObject({ errorCode: 'openalex_verification_unavailable', status: 503 });
  });

  it('rejects SerpAPI data belonging to a different token', async () => {
    await expect(validateReferenceCredentials({ serpapi_key: serpapiKey }, {
      fetchImpl: async () => Response.json({ ...serpapiBody, api_key: 'another-account-token' }),
    })).rejects.toMatchObject({ errorCode: 'serpapi_verification_unavailable', status: 503 });
  });

  it.each([{}, { api_key: null }, { api_key: '' }, { api_key: 'bad key' }, { serpapi_key: 12 },
    { api_key: openalexKey, serpapi_key: 'x'.repeat(513) }])('validates all local fields before contacting any provider for %j', async values => {
    const fetchImpl = vi.fn();
    await expect(validateReferenceCredentials(values, { fetchImpl })).rejects.toMatchObject({ status: 400 });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
