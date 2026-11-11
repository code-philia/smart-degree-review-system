const { randomUUID } = require('crypto');
const nodemailer = require('nodemailer');
const { get,run,all } = require('../database');
const users = require('../auth/sessionRepository');
const reports = require('../normative/paperLintReportRepository');
const { notificationEmail } = require('./emailPolicy');
const { mailConfig } = require('./mailConfig');
const { reportEmail } = require('./reportEmailTemplate');
const { createSjtuNotificationSender } = require('./sjtuNotificationSender');
const sjtuSend = createSjtuNotificationSender();
const { onReportEmailReady } = require('./reportEmailWakeup');
const RETRY_DELAYS = [60_000,300_000,1_800_000,7_200_000];
const MAX_ATTEMPTS = 5;
const LEASE_MS = 120_000;

async function smtpSend(mail, settings) {
  const transport = nodemailer.createTransport({host:settings.host,port:settings.port,secure:settings.port===465,
    requireTLS:settings.port!==465,auth:{user:settings.user,pass:settings.password},
    connectionTimeout:15_000,greetingTimeout:15_000,socketTimeout:20_000,
    disableFileAccess:true,disableUrlAccess:true,logger:false,debug:false});
  try {
    const receipt = await transport.sendMail(mail);
    if (!receipt.accepted?.length || receipt.rejected?.length) throw Object.assign(new Error('Mail recipient rejected'),{code:'EENVELOPE'});
  } finally { transport.close(); }
}

function sendReportMail(mail, settings) {
  return settings.provider==='sjtu-notification' ? sjtuSend(mail,settings) : smtpSend(mail,settings);
}
function createReportEmailService({send=sendReportMail, config=mailConfig, now=()=>Date.now()}={}) {
  let running = null;
  let wakePending = false;
  async function processPending() {
    const settings = config();
    if (!settings) return;
    const notBefore=settings.notBefore || '';
    const blocked=await all(`SELECT o.job_id,u.id,u.username,u.role,u.email FROM report_email_outbox o
      JOIN auth_users u ON u.id=o.user_id WHERE o.status='blocked' AND o.error_code='missing_recipient' AND o.created_at>=?`,[notBefore]);
    for(const row of blocked){
      if(notificationEmail(row))await run("UPDATE report_email_outbox SET status='pending',next_attempt_at=?,error_code=NULL WHERE job_id=? AND status='blocked'",[new Date(now()).toISOString(),row.job_id]);
    }
    while (true) {
      const time = new Date(now()).toISOString();
      await run("UPDATE report_email_outbox SET status='failed',error_code='delivery_interrupted',claim_token=NULL,lease_until=NULL,updated_at=? WHERE status='sending' AND lease_until<=? AND attempts>=? AND created_at>=?",[time,time,MAX_ATTEMPTS,notBefore]);
      const token=randomUUID();
      const row=await get(`UPDATE report_email_outbox SET status='sending',attempts=attempts+1,
        claim_token=?,lease_until=?,updated_at=? WHERE job_id=(SELECT job_id FROM report_email_outbox
        WHERE attempts<? AND created_at>=? AND ((status='pending' AND next_attempt_at<=?) OR (status='sending' AND lease_until<=?))
        ORDER BY created_at,job_id LIMIT 1) RETURNING *`,[token,new Date(now()+LEASE_MS).toISOString(),time,MAX_ATTEMPTS,notBefore,time,time]);
      if (!row) return;
      try {
        const report=await reports.findPaperLintReportByIdForUser(row.report_id,row.user_id);
        if (!report) {await finish(row,'cancelled','report_unavailable');continue;}
        const recipient=notificationEmail(await users.findUserById(row.user_id));
        if (!recipient) {await finish(row,'blocked','missing_recipient',false);continue;}
        await run('UPDATE report_email_outbox SET recipient=? WHERE job_id=? AND claim_token=?',[recipient,row.job_id,token]);
        await send(reportEmail(report,recipient,settings,row.job_id),settings);
        await finish(row,'sent',null);
      } catch (error) {
        const errorCode=['notification_authentication','notification_unavailable','recipient_rejected'].includes(error?.code)
          ? error.code : error?.code==='EAUTH' ? 'smtp_authentication' : error?.code==='EENVELOPE' ? 'recipient_rejected' : 'smtp_unavailable';
        const terminal=row.attempts>=MAX_ATTEMPTS;
        await run(`UPDATE report_email_outbox SET status=?,error_code=?,next_attempt_at=?,lease_until=NULL,claim_token=NULL,updated_at=?
          WHERE job_id=? AND claim_token=?`,[terminal?'failed':'pending',errorCode,new Date(now()+(RETRY_DELAYS[row.attempts-1] || 7_200_000)).toISOString(),new Date(now()).toISOString(),row.job_id,token]);
      }
    }
  }
  async function finish(row,status,errorCode,consumeAttempt=true) {
    const time=new Date(now()).toISOString();
    await run(`UPDATE report_email_outbox SET status=?,error_code=?,attempts=attempts-?,sent_at=?,lease_until=NULL,claim_token=NULL,updated_at=?
      WHERE job_id=? AND claim_token=?`,[status,errorCode,consumeAttempt?0:1,status==='sent'?time:null,time,row.job_id,row.claim_token]);
  }
  function drain() {
    if (!running) running=processPending().finally(()=>{running=null;if(wakePending){wakePending=false;wake();}});
    return running;
  }
  function wake() {
    if (running) {wakePending=true;return;}
    void drain().catch(()=>console.error('Report email worker temporarily unavailable'));
  }
  function start() {
    const unsubscribe=onReportEmailReady(wake);
    wake();const timer=setInterval(wake,15_000);timer.unref();
    return ()=>{unsubscribe();clearInterval(timer);wakePending=false;};
  }
  return {drain,start};
}
module.exports = { createReportEmailService, smtpSend, sendReportMail };
