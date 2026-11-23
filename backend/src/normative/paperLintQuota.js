const {get}=require('../database/db_runtime');
const {BILLABLE_RULE_IDS,getAccountCredit}=require('./paperLintCredit');
// Compatibility: report counts are no longer an allowance.
const DAILY_REPORT_LIMIT=0;
async function getDailyQuota(userId,at=new Date()){
  if(!await get('SELECT id FROM auth_users WHERE id=?',[userId]))throw Object.assign(new Error('未找到当前用户'),{status:404});
  return {limited:false,limit:0,used:0,reserved:0,remaining:null,period:'lifetime',day:null,resets_at:null,
    server_time:new Date(at).toISOString(),timezone:'Asia/Shanghai'};
}
function quotaAdmission(userId,_at,selectedRuleIds=[]){
  const paid=selectedRuleIds.some(id=>BILLABLE_RULE_IDS.has(id));
  return {sql:paid?'EXISTS (SELECT 1 FROM paper_lint_credit_accounts WHERE user_id=? AND granted_nano-spent_nano-reserved_nano>0)'
    :'EXISTS (SELECT 1 FROM auth_users WHERE id=?)',params:[userId]};
}
async function quotaExceeded(userId){
  return Object.assign(new Error('可用额度不足，无法开始模型检测；您仍可使用不消耗额度的规则。'),
    {status:402,code:'PAPER_LINT_CREDIT',credit:await getAccountCredit(userId)});
}
module.exports={DAILY_REPORT_LIMIT,getDailyQuota,quotaAdmission,quotaExceeded};
