const { codes } = require('./nationality-codes.json');

const recognized = new Set(codes.flat());
const chinese = new Set(['CN', 'CHN', '156']);
// Region codes alone do not establish a person's nationality.
const ambiguous = new Set(['HK', 'HKG', '344', 'MO', 'MAC', '446', 'TW', 'TWN', '158']);

function nationalityLocale(value) {
  if (typeof value !== 'string' || value.length > 16) return null;
  let code = value.trim().toUpperCase();
  if (/^\d{1,3}$/.test(code)) code = code.padStart(3, '0');
  if (chinese.has(code)) return 'zh';
  return recognized.has(code) && !ambiguous.has(code) ? 'en' : null;
}

function defaultLocaleFromProfile(profile) {
  if (!Array.isArray(profile?.identities)) return null;
  const identities = profile.identities.filter(value => value && typeof value === 'object' && !Array.isArray(value));
  const defaults = identities.filter(identity => identity.isDefault === true);
  if (defaults.length > 1) return null;
  if (defaults.length === 1) return nationalityLocale(defaults[0].gjm);
  const locales = new Set(identities.map(identity => nationalityLocale(identity.gjm)).filter(Boolean));
  return locales.size === 1 ? [...locales][0] : null;
}

module.exports = { defaultLocaleFromProfile };
