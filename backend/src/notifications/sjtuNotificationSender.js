const {createHash} = require('crypto');
const {normalizeEmail} = require('./emailPolicy');
const TOKEN_URL = 'https://jaccount.sjtu.edu.cn/oauth2/token';
const NOTIFICATION_URL = 'https://api.sjtu.edu.cn/v1/notification';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function unavailable(code='notification_unavailable') {
  return Object.assign(new Error('Report notification temporarily unavailable'), {code});
}

function createSjtuNotificationSender({request=(...args)=>fetch(...args),now=Date.now}={}) {
  let cached = null;
  async function fetchJson(url, options, timeoutMs=20000) {
    let response;
    try { response = await request(url, {...options,redirect:'error',signal:AbortSignal.timeout(timeoutMs)}); }
    catch { throw unavailable(); }
    if (!response.ok) throw Object.assign(unavailable(response.status===401 || response.status===403 ? 'notification_authentication' : undefined),{status:response.status});
    try { return await response.json(); } catch { throw unavailable(); }
  }
  async function accessToken(settings, rejectedToken) {
    const fingerprint=createHash('sha256').update(JSON.stringify([settings.clientId,settings.clientSecret,settings.username,settings.password])).digest('hex');
    if (!cached || cached.fingerprint!==fingerprint) cached={fingerprint,token:null,expiresAt:0,pending:null};
    const entry=cached;
    if (rejectedToken && entry.token===rejectedToken) {entry.token=null;entry.expiresAt=0;}
    if (entry.token && entry.expiresAt>now()) return entry.token;
    if (!entry.pending) {
      entry.pending=(async()=>{
        const data=await fetchJson(TOKEN_URL, {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded',Accept:'application/json',
          Authorization:'Basic '+Buffer.from(`${settings.clientId}:${settings.clientSecret}`).toString('base64')},
          body:new URLSearchParams({grant_type:'password',scope:'send_notification',username:settings.username,password:settings.password}).toString()},15000);
        const lifetime=Number(data?.expires_in);
        if (typeof data?.access_token!=='string' || !data.access_token || !Number.isFinite(lifetime) || lifetime<=0
            || String(data.token_type).toLowerCase()!=='bearer') throw unavailable('notification_authentication');
        entry.token=data.access_token;entry.expiresAt=now()+Math.max(0,lifetime*1000-60000);
        return entry.token;
      })().finally(()=>{entry.pending=null;});
    }
    return entry.pending;
  }
  return async function send(mail, settings) {
    const recipient=normalizeEmail(mail.to);
    if (!recipient) throw Object.assign(new Error('Invalid report recipient'),{code:'recipient_rejected'});
    const identity=/^<report-([^@]+)@/.exec(mail.messageId || '')?.[1];
    const payload={...(identity && UUID.test(identity)?{id:identity}:{}),name:mail.subject,content:mail.text,html:mail.html,emails:[recipient],channels:['email']};
    let token=await accessToken(settings);
    for (let attempt=0;attempt<2;attempt++) {
      let data;
      try { data=await fetchJson(NOTIFICATION_URL,{method:'PUT',headers:{'Content-Type':'application/json',Accept:'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify(payload)}); }
      catch(error) {
        if (attempt===0 && error.status===401) {token=await accessToken(settings,token);continue;}
        throw error;
      }
      const notificationId=data?.entities?.[0]?.id;
      if (data?.errno!==0 || data?.entities?.length!==1 || typeof notificationId!=='string' || !UUID.test(notificationId)) throw unavailable();
      // Receipt means the campus API accepted the notification, not inbox delivery.
      return {notificationId};
    }
    throw unavailable('notification_authentication');
  };
}
module.exports={createSjtuNotificationSender};
