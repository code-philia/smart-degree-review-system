const fs = require('fs');
const { normalizeEmail } = require('./emailPolicy');

function mailConfig() {
  if (process.env.REPORT_EMAIL_ENABLED !== '1') return null;
  const host = process.env.SMTP_HOST?.trim();
  const user = process.env.SMTP_USER?.trim();
  let password = process.env.SMTP_PASSWORD;
  if (!password && process.env.SMTP_PASSWORD_FILE) {
    try { password = fs.readFileSync(process.env.SMTP_PASSWORD_FILE, 'utf8').trimEnd(); } catch { return null; }
  }
  const port = Number(process.env.SMTP_PORT || 465);
  const from = normalizeEmail(process.env.SMTP_FROM_ADDRESS || 'gs.xwb1@sjtu.edu.cn');
  let origin;
  try {
    const url = new URL(process.env.APP_PUBLIC_URL);
    if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) return null;
    origin = url.origin;
  } catch { return null; }
  if (!host || /[\s/\\]/.test(host) || !user || !password || !from || !Number.isInteger(port) || port < 1 || port > 65535) return null;
  return { host, port, user, password, from, origin,
    fromName: (process.env.SMTP_FROM_NAME || '研究生学位信息系统').replace(/[\r\n\u0000]/g,' ').slice(0,100) };
}
module.exports = { mailConfig };
