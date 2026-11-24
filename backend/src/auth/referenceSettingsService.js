const crypto = require('crypto');
const fs = require('node:fs/promises');
const { constants: fileConstants } = require('node:fs');
const { all, withTransaction } = require('../database');
const { sharedReferenceQuotaAllowed } = require('./referencePersonalAccess');

const MAX_API_KEY_LENGTH = 512;
const MAX_PRIVATE_CONFIG_BYTES = 64 * 1024;
const DEFAULT_EVIDENCE_CONFIG = '/data/apps/smart-degree-review/config/paper-model-evidence.env';

function settingsError(errorCode, status = 503) {
  // Never retain a crypto/driver error as a cause: it can contain credentials.
  const error = new Error('Reference settings request failed');
  error.errorCode = errorCode;
  error.status = status;
  return error;
}

function encryptionKey() {
  const value = String(process.env.REFERENCE_SETTINGS_ENCRYPTION_KEY || '').trim();
  if (!/^[A-Za-z0-9+/]{43}=$/.test(value)) return null;
  const key = Buffer.from(value, 'base64');
  return key.length === 32 && key.toString('base64') === value ? key : null;
}

function normalizeApiKey(value) {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  // Provider keys are opaque tokens. Bound their size and reject whitespace,
  // control characters and non-ASCII input without assuming a UUID format.
  return normalized.length > 0 && normalized.length <= MAX_API_KEY_LENGTH
    && /^[\x21-\x7e]+$/.test(normalized) ? normalized : null;
}

function validUserId(userId) {
  return typeof userId === 'string' && userId.length > 0 && userId.length <= 512;
}

function encryptApiKey(userId, provider, apiKey, key) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.from(JSON.stringify([userId, provider]), 'utf8'));
  const ciphertext = Buffer.concat([cipher.update(apiKey, 'utf8'), cipher.final()]);
  return ['v1', iv.toString('base64'), cipher.getAuthTag().toString('base64'), ciphertext.toString('base64')].join('.');
}

function decryptApiKey(userId, provider, envelope, key) {
  if (!key || typeof envelope !== 'string' || envelope.length > 2048) return null;
  try {
    const parts = envelope.split('.');
    if (parts.length !== 4 || parts[0] !== 'v1') return null;
    const [iv, tag, ciphertext] = parts.slice(1).map(value => {
      const decoded = Buffer.from(value, 'base64');
      if (decoded.toString('base64') !== value) throw new Error('Invalid envelope');
      return decoded;
    });
    if (iv.length !== 12 || tag.length !== 16 || ciphertext.length < 1 || ciphertext.length > MAX_API_KEY_LENGTH) return null;
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAAD(Buffer.from(JSON.stringify([userId, provider]), 'utf8'));
    decipher.setAuthTag(tag);
    const apiKey = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
    return normalizeApiKey(apiKey) === apiKey ? apiKey : null;
  } catch {
    return null;
  }
}

function maskApiKey(apiKey) {
  return apiKey.length > 4 ? `••••${apiKey.slice(-4)}` : '••••';
}

function decryptRows(userId, rows, key) {
  const result = {};
  for (const provider of ['openalex', 'serpapi']) {
    const row = rows.find(value => value.provider === provider);
    const apiKey = row ? decryptApiKey(userId, provider, row.encrypted_api_key, key) : null;
    result[provider] = { configured: Boolean(row), apiKey, status: !row ? 'not_configured' : apiKey ? 'available' : 'unavailable' };
  }
  return result;
}

function publicSettings(userId, rows, key, sharedQuotaAllowed = false) {
  const credentials = decryptRows(userId, rows, key);
  return {
    configured: credentials.openalex.configured,
    key_hint: credentials.openalex.apiKey ? maskApiKey(credentials.openalex.apiKey) : null,
    serpapi_configured: credentials.serpapi.configured,
    serpapi_key_hint: credentials.serpapi.apiKey ? maskApiKey(credentials.serpapi.apiKey) : null,
    can_verify_references: sharedQuotaAllowed || Boolean(credentials.openalex.apiKey || credentials.serpapi.apiKey),
    storage_available: Boolean(key) && Object.values(credentials).every(value => value.status !== 'unavailable'),
  };
}

async function getReferenceSettings(userId) {
  if (!validUserId(userId)) throw settingsError('account_changed', 409);
  try {
    const rows = await all('SELECT provider,encrypted_api_key FROM user_reference_settings WHERE user_id=?', [userId]);
    return publicSettings(userId, rows, encryptionKey(), await sharedReferenceQuotaAllowed(userId));
  } catch {
    throw settingsError('storage_unavailable');
  }
}

async function saveReferenceSettings(userId, values) {
  if (!validUserId(userId)) throw settingsError('account_changed', 409);
  const updates = [];
  for (const [provider, field, errorCode] of [['openalex', 'api_key', 'invalid_api_key'], ['serpapi', 'serpapi_key', 'invalid_serpapi_key']]) {
    if (values && Object.hasOwn(values, field)) {
      const apiKey = normalizeApiKey(values[field]);
      if (!apiKey) throw settingsError(errorCode, 400);
      updates.push({ provider, apiKey });
    }
  }
  if (!updates.length) throw settingsError('invalid_api_key', 400);
  const key = encryptionKey();
  if (!key) throw settingsError('storage_unavailable');
  const sharedQuotaAllowed = await sharedReferenceQuotaAllowed(userId);
  try {
    return await withTransaction(async tx => {
      for (const { provider, apiKey } of updates) {
        const encrypted = encryptApiKey(userId, provider, apiKey, key);
        await tx.run(`INSERT INTO user_reference_settings (user_id,provider,encrypted_api_key) VALUES (?,?,?)
          ON CONFLICT(user_id,provider) DO UPDATE SET encrypted_api_key=excluded.encrypted_api_key,updated_at=CURRENT_TIMESTAMP`, [userId, provider, encrypted]);
      }
      return publicSettings(userId, await tx.all('SELECT provider,encrypted_api_key FROM user_reference_settings WHERE user_id=?', [userId]), key, sharedQuotaAllowed);
    });
  } catch {
    throw settingsError('storage_unavailable');
  }
}

async function deleteReferenceSettings(userId, provider = 'openalex') {
  if (!validUserId(userId)) throw settingsError('account_changed', 409);
  if (!['openalex', 'serpapi'].includes(provider)) throw settingsError('invalid_provider', 400);
  const sharedQuotaAllowed = await sharedReferenceQuotaAllowed(userId);
  try {
    return await withTransaction(async tx => {
      await tx.run('DELETE FROM user_reference_settings WHERE user_id=? AND provider=?', [userId, provider]);
      return publicSettings(userId, await tx.all('SELECT provider,encrypted_api_key FROM user_reference_settings WHERE user_id=?', [userId]), encryptionKey(), sharedQuotaAllowed);
    });
  } catch {
    throw settingsError('storage_unavailable');
  }
}

function parsePlatformKeys(value, separator = /[\s,;]+/) {
  if (typeof value !== 'string' || !value.trim()) return [];
  const keys = [...new Set(value.split(separator).map(part => part.trim()).filter(Boolean))];
  return keys.length <= 8 && keys.every(key => /^[A-Za-z0-9._~-]{1,512}$/.test(key)) ? keys : [];
}

async function privatePlatformKeys() {
  // Defined-but-empty variables explicitly disable legacy file fallback.
  if (process.env.OPENALEX_API_KEYS !== undefined) return parsePlatformKeys(process.env.OPENALEX_API_KEYS);
  if (process.env.OPENALEX_API_KEY !== undefined) return parsePlatformKeys(process.env.OPENALEX_API_KEY);
  let file;
  try {
    const filename = process.env.PAPER_COMPILER_EVIDENCE_CONFIG ?? DEFAULT_EVIDENCE_CONFIG;
    const before = await fs.lstat(filename);
    if (before.isSymbolicLink() || !before.isFile() || (before.mode & 0o077) || before.size > MAX_PRIVATE_CONFIG_BYTES) return [];
    file = await fs.open(filename, fileConstants.O_RDONLY | (fileConstants.O_NOFOLLOW || 0));
    const opened = await file.stat();
    if (!opened.isFile() || (opened.mode & 0o077) || opened.size > MAX_PRIVATE_CONFIG_BYTES
      || opened.dev !== before.dev || opened.ino !== before.ino) return [];
    // Read at most64KiB plus one detection byte, even if a file grows after stat.
    const buffer = Buffer.alloc(MAX_PRIVATE_CONFIG_BYTES + 1);
    let offset = 0;
    while (offset < buffer.length) {
      const { bytesRead } = await file.read(buffer, offset, buffer.length - offset, offset);
      if (!bytesRead) break;
      offset += bytesRead;
    }
    if (offset > MAX_PRIVATE_CONFIG_BYTES) return [];
    const text = new TextDecoder('utf-8', { fatal: true }).decode(buffer.subarray(0, offset));
    if (text.includes('\0')) return [];
    const settings = new Map();
    for (const source of text.split(/\r?\n/)) {
      const line = source.trim();
      if (!/^(?:OPENALEX_API_KEYS?)(?:\s|=|$)/.test(line)) continue;
      const match = /^(OPENALEX_API_KEYS?)\s*=\s*(.*?)\s*$/.exec(line);
      if (!match || settings.has(match[1])) return [];
      let value = match[2];
      if (/^["']/.test(value)) {
        if (value.length < 2 || value.at(-1) !== value[0]) return [];
        value = value.slice(1, -1);
      }
      settings.set(match[1], value);
    }
    return parsePlatformKeys(settings.get('OPENALEX_API_KEYS') || settings.get('OPENALEX_API_KEY'), ',');
  } catch {
    // Missing, unsafe, malformed and unreadable configuration all preserve the
    // key-free catalog fallback. Do not retain filenames, contents or raw errors.
    return [];
  } finally {
    if (file) await file.close().catch(() => {});
  }
}

// Private runtime interface. Never pass this object into results, job progress,
// errors, caches or HTTP responses; the provider service alone consumes keys.
async function getReferenceCredentials(userId, { includePlatformKeys = true } = {}) {
  const credentials = { personalKey: null, serpapiKey: null, platformKeys: includePlatformKeys ? await privatePlatformKeys() : [],
    credential_status: 'not_configured', serpapi_credential_status: 'not_configured' };
  if (!validUserId(userId)) return credentials;
  let rows;
  try {
    rows = await all('SELECT provider,encrypted_api_key FROM user_reference_settings WHERE user_id=?', [userId]);
  } catch {
    return { ...credentials, credential_status: 'storage_unavailable', serpapi_credential_status: 'storage_unavailable' };
  }
  const decrypted = decryptRows(userId, rows, encryptionKey());
  return { ...credentials, personalKey: decrypted.openalex.apiKey, serpapiKey: decrypted.serpapi.apiKey,
    credential_status: decrypted.openalex.status, serpapi_credential_status: decrypted.serpapi.status };
}

module.exports = { getReferenceSettings, saveReferenceSettings, deleteReferenceSettings, getReferenceCredentials };
