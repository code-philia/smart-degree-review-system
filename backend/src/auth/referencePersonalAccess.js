const REFERENCE_RULE_ID = 'reference_verification_check';
const { trialUserAllowed } = require('./trialLoginPolicy');

async function sharedReferenceQuotaAllowed(userId) {
  if (typeof userId !== 'string' || !userId || userId.length > 512) return false;
  try {
    const user = await require('../database').get('SELECT id,username,role FROM auth_users WHERE id=?', [userId]);
    // Read the persisted identity, never a request flag, username or role alone.
    return trialUserAllowed(user);
  } catch { return false; }
}

function referenceKeyRequired() {
  return Object.assign(new Error('请先点击右上角钥匙图标，保存自己的 OpenAlex 或 SerpAPI 密钥后再使用此规则。'),
    { status: 400, code: 'reference_key_required', errorCode: 'reference_key_required' });
}

function personalReferenceCredentials(values = {}, allowSharedQuota = false) {
  const token = value => typeof value === 'string' && value.trim().length <= 512
    && /^[\x21-\x7e]+$/.test(value.trim()) ? value.trim() : null;
  const personalKey = token(values.personalKey);
  const serpapiKey = token(values.serpapiKey);
  if (!personalKey && !serpapiKey && !allowSharedQuota) throw referenceKeyRequired();
  // Ordinary accounts receive only their decrypted personal credentials. The
  // server's persisted-identity decision alone enables the four local accounts.
  return { personalKey, serpapiKey, ...(allowSharedQuota ? { allowSharedQuota: true,
    platformKeys: Array.isArray(values.platformKeys) ? values.platformKeys.map(token).filter(Boolean).slice(0, 8) : [] } : {}) };
}

async function requirePersonalReferenceCredentials(userId) {
  const allowSharedQuota = await sharedReferenceQuotaAllowed(userId);
  const values = await require('./referenceSettingsService').getReferenceCredentials(userId, { includePlatformKeys: allowSharedQuota });
  return personalReferenceCredentials(values, allowSharedQuota);
}

async function requireReferenceRuleAccess(userId, selectedRuleIds) {
  if (Array.isArray(selectedRuleIds) && selectedRuleIds.some(id => String(id).trim() === REFERENCE_RULE_ID)) {
    await requirePersonalReferenceCredentials(userId);
  }
}

module.exports = { personalReferenceCredentials, requirePersonalReferenceCredentials, requireReferenceRuleAccess, sharedReferenceQuotaAllowed };
