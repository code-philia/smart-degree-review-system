const {get}=require('../database/db_runtime');
const {ADMIN_ROLES}=require('../auth/loginPolicy');
const {TRIAL_ACCOUNTS,trialUserAllowed}=require('../auth/trialLoginPolicy');
const DAILY_REPORT_LIMIT=3;
// Keep the existing internal API names to avoid changing callers.
// The allowance is now lifetime, starting at the one-time persisted cutover.
async function getDailyQuota(userId,at=new Date()) {

  const row=await get(`SELECT u.id,u.username,u.role,p.starts_at,
    SUM(CASE WHEN j.status='completed' THEN 1 ELSE 0 END) AS used,
    SUM(CASE WHEN j.status IN ('pending','running') THEN 1 ELSE 0 END) AS reserved
    FROM auth_users u CROSS JOIN paper_lint_quota_policy p LEFT JOIN paper_lint_jobs j ON j.user_id=u.id
      AND j.created_at>=p.starts_at AND j.cancelled_at IS NULL
    WHERE u.id=? AND p.id=1 GROUP BY u.id`,[userId]);
  if(!row)throw Object.assign(new Error('未找到当前用户'),{status:404});
  const limited=!ADMIN_ROLES.includes(row.role)&&!trialUserAllowed(row);
  const used=limited?Number(row.used||0):0,reserved=limited?Number(row.reserved||0):0;
  return {limited,limit:DAILY_REPORT_LIMIT,used,reserved,remaining:limited?Math.max(0,DAILY_REPORT_LIMIT-used-reserved):null,
    period:'lifetime',starts_at:row.starts_at,day:null,resets_at:null,server_time:new Date(at).toISOString(),timezone:'Asia/Shanghai'};
}

// Admission and reservation are a single SQLite statement, including across processes.
// Avoid an async transaction here so cancellation/completion keep their existing behavior.
function quotaAdmission(userId,at=new Date()) {

  const trialIdentities=Object.entries(TRIAL_ACCOUNTS);
  return {sql:`EXISTS (SELECT 1 FROM auth_users WHERE id=? AND (role IN (${ADMIN_ROLES.map(()=>'?').join(',')})
      OR (id COLLATE BINARY=username COLLATE BINARY AND (${trialIdentities.map(()=>'(username COLLATE BINARY=? AND role=?)').join(' OR ')}))))
    OR (SELECT COUNT(*) FROM paper_lint_jobs WHERE user_id=? AND created_at>=(SELECT starts_at FROM paper_lint_quota_policy WHERE id=1)
      AND cancelled_at IS NULL AND status IN ('pending','running','completed')) < ?`,
    params:[userId,...ADMIN_ROLES,...trialIdentities.flat(),userId,DAILY_REPORT_LIMIT]};
}

async function quotaExceeded(userId) {
  const quota=await getDailyQuota(userId);
  const message=quota.used>=quota.limit
    ?'检测次数已用完，每个账号累计可生成 3 份报告。'
    :quota.remaining===0
      ?'当前可用检测次数已被进行中的任务占用，请在任务结束或取消后重试。'
      :'检测额度已更新，请重试。';
  return Object.assign(new Error(message),{status:429,code:'PAPER_LINT_QUOTA',quota});
}
module.exports={DAILY_REPORT_LIMIT,getDailyQuota,quotaAdmission,quotaExceeded};
