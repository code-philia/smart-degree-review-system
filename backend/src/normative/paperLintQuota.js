const {get}=require('../database/db_runtime');
const {ADMIN_ROLES}=require('../auth/loginPolicy');
const {TRIAL_ACCOUNTS,trialUserAllowed}=require('../auth/trialLoginPolicy');
const DAILY_REPORT_LIMIT=3;
const DAY_MS=24*60*60*1000;
const CHINA_OFFSET_MS=8*60*60*1000;

function quotaWindow(at=new Date()) {
  const now=new Date(at);
  if(!Number.isFinite(now.getTime()))throw new TypeError('Invalid quota time');
  const day=new Date(now.getTime()+CHINA_OFFSET_MS).toISOString().slice(0,10);
  const start=new Date(day+'T00:00:00+08:00');
  return {day,start:start.toISOString(),resets_at:new Date(start.getTime()+DAY_MS).toISOString(),server_time:now.toISOString(),timezone:'Asia/Shanghai'};
}

async function getDailyQuota(userId,at=new Date()) {
  const period=quotaWindow(at);
  const row=await get(`SELECT u.id,u.username,u.role,
    SUM(CASE WHEN j.status='completed' THEN 1 ELSE 0 END) AS used,
    SUM(CASE WHEN j.status IN ('pending','running') THEN 1 ELSE 0 END) AS reserved
    FROM auth_users u LEFT JOIN paper_lint_jobs j ON j.user_id=u.id
      AND j.created_at>=? AND j.created_at<? AND j.cancelled_at IS NULL
    WHERE u.id=? GROUP BY u.id`,[period.start,period.resets_at,userId]);
  if(!row)throw Object.assign(new Error('未找到当前用户'),{status:404});
  const limited=!ADMIN_ROLES.includes(row.role)&&!trialUserAllowed(row);
  const used=limited?Number(row.used||0):0,reserved=limited?Number(row.reserved||0):0;
  return {limited,limit:DAILY_REPORT_LIMIT,used,reserved,remaining:limited?Math.max(0,DAILY_REPORT_LIMIT-used-reserved):null,
    day:period.day,resets_at:period.resets_at,server_time:period.server_time,timezone:period.timezone};
}

// Admission and reservation are a single SQLite statement, including across processes.
// Avoid an async transaction here so cancellation/completion keep their existing behavior.
function quotaAdmission(userId,at=new Date()) {
  const period=quotaWindow(at);
  const trialIdentities=Object.entries(TRIAL_ACCOUNTS);
  return {sql:`EXISTS (SELECT 1 FROM auth_users WHERE id=? AND (role IN (${ADMIN_ROLES.map(()=>'?').join(',')})
      OR (id COLLATE BINARY=username COLLATE BINARY AND (${trialIdentities.map(()=>'(username COLLATE BINARY=? AND role=?)').join(' OR ')}))))
    OR (SELECT COUNT(*) FROM paper_lint_jobs WHERE user_id=? AND created_at>=? AND created_at<?
      AND cancelled_at IS NULL AND status IN ('pending','running','completed')) < ?`,
    params:[userId,...ADMIN_ROLES,...trialIdentities.flat(),userId,period.start,period.resets_at,DAILY_REPORT_LIMIT]};
}

async function quotaExceeded(userId) {
  const quota=await getDailyQuota(userId);
  const message=quota.used>=quota.limit
    ?'今日检测次数已用完，请于北京时间明日00:00后重试。'
    :quota.remaining===0
      ?'当前可用检测次数已被进行中的任务占用，请在任务结束或取消后重试。'
      :'检测额度已更新，请重试。';
  return Object.assign(new Error(message),{status:429,code:'PAPER_LINT_DAILY_QUOTA',quota});
}
module.exports={DAILY_REPORT_LIMIT,quotaWindow,getDailyQuota,quotaAdmission,quotaExceeded};
