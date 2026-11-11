const fs = require('fs');
const { normalizeEmail } = require('./emailPolicy');

function secret(value, filename) {
  if (value) return value;
  if (filename) {try {return fs.readFileSync(filename,'utf8').trimEnd();} catch {return null;}}
  return null;
}
function mailConfig() {
  if (process.env.REPORT_EMAIL_ENABLED !== '1') return null;
  const provider=process.env.REPORT_EMAIL_PROVIDER?.trim() || 'smtp';
  if (!['smtp','sjtu-notification'].includes(provider)) return null;
  let origin;
  try {
    const url=new URL(process.env.APP_PUBLIC_URL);
    if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.pathname!=='/' || url.search || url.hash) return null;
    origin=url.origin;
  } catch {return null;}
  const notBefore=process.env.REPORT_EMAIL_NOT_BEFORE?.trim() || '';
  if (notBefore && (!Number.isFinite(Date.parse(notBefore)) || new Date(notBefore).toISOString()!==notBefore)) return null;
  const common={provider,origin,notBefore,fromName:(process.env.SMTP_FROM_NAME || '研究生学位信息系统').replace(/[\r\n\u0000]/g,' ').slice(0,100)};
  if (provider==='sjtu-notification') {
    const clientId=process.env.JACCOUNT_CLIENT_ID?.trim(),clientSecret=process.env.JACCOUNT_CLIENT_SECRET?.trim();
    const username=process.env.JACCOUNT_NOTIFICATION_USERNAME?.trim();
    const password=secret(process.env.JACCOUNT_NOTIFICATION_PASSWORD,process.env.JACCOUNT_NOTIFICATION_PASSWORD_FILE);
    if (!clientId || !clientSecret || !username || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(username) || !password) return null;
    const from=normalizeEmail(`${username}@sjtu.edu.cn`);
    return from?{...common,clientId,clientSecret,username,password,from}:null;
  }
  const host=process.env.SMTP_HOST?.trim(),user=process.env.SMTP_USER?.trim();
  const password=secret(process.env.SMTP_PASSWORD,process.env.SMTP_PASSWORD_FILE);
  const port=Number(process.env.SMTP_PORT || 465);
  const from=normalizeEmail(process.env.SMTP_FROM_ADDRESS || 'gs.xwb1@sjtu.edu.cn');
  if (!host || /[\s/\\]/.test(host) || !user || !password || !from || !Number.isInteger(port) || port<1 || port>65535) return null;
  return {...common,host,port,user,password,from};
}
module.exports={mailConfig};
