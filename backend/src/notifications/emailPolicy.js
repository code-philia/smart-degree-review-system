const { ADMIN_ROLES } = require('../auth/loginPolicy');
const ADMIN_EMAIL = '123090058@link.cuhk.edu.cn';
const LOCAL_NOTIFICATION_ACCOUNTS = new Set(['student01','supervisor01','college_admin01','school_admin01']);

function normalizeEmail(value) {
  if (typeof value !== 'string') return null;
  const email = value.trim();
  if (email.length > 254 || /[\s\u0000-\u001f\u007f,;<>]/.test(email)) return null;
  const parts = email.split('@');
  if (parts.length !== 2) return null;
  const [local, domain] = parts;
  if (!local || local.length > 64 || !/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)
      || local.startsWith('.') || local.endsWith('.') || local.includes('..')) return null;
  const labels = domain.split('.');
  if (labels.length < 2 || labels.some(label => label.length > 63 || !/^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label))) return null;
  return `${local}@${domain.toLowerCase()}`;
}

function campusEmail(profile) {
  const explicit = normalizeEmail(profile?.email);
  if (explicit) return explicit;
  const account = profile?.account;
  return typeof account === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(account)
    ? normalizeEmail(`${account}@sjtu.edu.cn`) : null;
}

function notificationEmail(user) {
  if(fixedNotificationEmail(user))return ADMIN_EMAIL;
  return normalizeEmail(user?.email) || (campusIdentity(user)?campusEmail({account:user.username.slice('jaccount:'.length)}):null);
}
function campusIdentity(user){return typeof user?.id==='string'&&user.id.startsWith('jaccount:')&&typeof user.username==='string'&&user.username.startsWith('jaccount:');}
function fixedNotificationEmail(user) { return Boolean(user) && (ADMIN_ROLES.includes(user.role)
  || (user.id===user.username&&LOCAL_NOTIFICATION_ACCOUNTS.has(user.username))); }

module.exports = { ADMIN_EMAIL, normalizeEmail, campusEmail, notificationEmail, fixedNotificationEmail, campusIdentity };
