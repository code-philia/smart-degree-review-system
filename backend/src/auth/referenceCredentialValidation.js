const PROVIDERS = [
  { field: 'api_key', provider: 'openalex', endpoint: 'https://api.openalex.org/rate-limit', invalid: 'invalid_api_key' },
  { field: 'serpapi_key', provider: 'serpapi', endpoint: 'https://serpapi.com/account.json', invalid: 'invalid_serpapi_key' },
];
const VERIFICATION_TIMEOUT_MS = 8000;
const MAX_RESPONSE_BYTES = 32 * 1024;

function credentialError(errorCode, status) {
  const error = new Error('Reference credential verification failed');
  error.errorCode = errorCode;
  error.status = status;
  return error;
}

function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function authenticatedResponse(config, body) {
  if (!object(body) || typeof body.api_key !== 'string' || !body.api_key.trim()) return false;
  if (config.provider === 'serpapi') {
    return body.api_key === config.apiKey && typeof body.account_id === 'string' && Boolean(body.account_id.trim())
      && typeof body.account_status === 'string' && Boolean(body.account_status.trim());
  }
  // OpenAlex documents a masked api_key, so do not require the complete secret
  // to be echoed. /rate-limit requires authentication; public catalog data does
  // not satisfy either authenticated quota schema.
  const quota = body.rate_limit;
  return object(quota) && [
    ['daily_budget_usd', 'daily_used_usd', 'daily_remaining_usd'],
    ['credits_limit', 'credits_used', 'credits_remaining'],
  ].some(fields => fields.every(field => Number.isFinite(quota[field])));
}

async function readBoundedJson(response, signal) {
  if (!/^application\/(?:[\w.+-]+\+)?json(?:\s*;|$)/i.test(response.headers.get('content-type') || '')
    || Number(response.headers.get('content-length')) > MAX_RESPONSE_BYTES) throw new Error('Unverified response');
  const reader = response.body.getReader();
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  try {
    const chunks = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        cancel();
        throw new Error('Unverified response');
      }
      chunks.push(Buffer.from(value));
    }
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks, size)));
  } finally {
    signal.removeEventListener('abort', cancel);
    reader.releaseLock();
  }
}

async function verifyCredential(config, fetchImpl) {
  const controller = new AbortController();
  let timer;
  let outcome = 'unavailable';
  try {
    const timeout = new Promise(resolve => {
      timer = setTimeout(() => {
        controller.abort();
        resolve('unavailable');
      }, VERIFICATION_TIMEOUT_MS);
    });
    outcome = await Promise.race([timeout, (async () => {
      const url = new URL(config.endpoint);
      url.searchParams.set('api_key', config.apiKey);
      // Fixed HTTPS account endpoints are free and never use a stored/platform
      // credential. Redirects must not send the submitted token to another host.
      const response = await fetchImpl(url.href, { method: 'GET', redirect: 'error',
        headers: { Accept: 'application/json' }, signal: controller.signal });
      if (response.redirected) return 'unavailable';
      if ([401, 403].includes(response.status)) return 'invalid';
      if (![200, 400].includes(response.status)) return 'unavailable';
      const body = await readBoundedJson(response, controller.signal);
      if (object(body) && Object.hasOwn(body, 'error') && body.error) return 'invalid';
      return response.status === 200 && authenticatedResponse(config, body) ? 'valid' : 'unavailable';
    })()]);
  } catch {
    // Provider bodies, URLs and transport errors can include the full token.
    // Discard them, including causes; only a fixed code leaves this boundary.
  } finally {
    clearTimeout(timer);
    controller.abort();
  }
  if (outcome === 'invalid') throw credentialError(config.invalid, 400);
  if (outcome !== 'valid') throw credentialError(`${config.provider}_verification_unavailable`, 503);
}

async function validateReferenceCredentials(values, { fetchImpl = globalThis.fetch } = {}) {
  const updates = [];
  for (const config of PROVIDERS) {
    if (!values || !Object.hasOwn(values, config.field)) continue;
    const apiKey = typeof values[config.field] === 'string' ? values[config.field].trim() : '';
    if (!apiKey || apiKey.length > 512 || !/^[\x21-\x7e]+$/.test(apiKey)) throw credentialError(config.invalid, 400);
    updates.push({ ...config, apiKey });
  }
  if (!updates.length) throw credentialError('invalid_api_key', 400);
  // Check every supplied field locally before any provider request, then await
  // all verification before the existing encrypted transaction may begin.
  await Promise.all(updates.map(config => verifyCredential(config, fetchImpl)));
}

module.exports = { validateReferenceCredentials };
