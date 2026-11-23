const {randomUUID}=require('crypto');
const {get,all,withTransaction}=require('../database/db_runtime');
const {getDbPath}=require('../database/init_db');
const policy=require('../../../shared/paper-lint-credit-policy.json');
const BILLABLE_RULE_IDS=new Set(Object.keys(policy.estimated_cny));
function money(nano){
  if(!Number.isSafeInteger(nano)||nano<0)throw new Error('Invalid account credit');
  return `${Math.floor(nano/1e9)}.${String(nano%1e9).padStart(9,'0')}`;
}
function processAlive(pid){
  if(!Number.isSafeInteger(pid)||pid<=0)return false;
  try{process.kill(pid,0);return true;}catch(error){return error.code!=='ESRCH';}
}
async function finishCreditOperation(operationId){
  if(!operationId)return;
  await withTransaction(async tx=>{
    const op=await tx.get('SELECT * FROM paper_lint_credit_operations WHERE id=?',[operationId]);
    if(!op||op.state==='closed')return;
    await tx.run("UPDATE paper_lint_credit_operations SET state='closing' WHERE id=?",[operationId]);
    const calls=await tx.all("SELECT * FROM paper_lint_credit_calls WHERE operation_id=? AND status='reserved'",[operationId]);
    for(const call of calls){
      // Refund only after the transport worker has exited, including on restart.
      if(processAlive(call.worker_pid))continue;
      const changed=await tx.run("UPDATE paper_lint_credit_calls SET status='unknown',failure_code='worker_stopped',updated_at=? WHERE id=? AND status='reserved'",[new Date().toISOString(),call.id]);
      if(changed.changes)await tx.run('UPDATE paper_lint_credit_accounts SET reserved_nano=reserved_nano-? WHERE user_id=?',[call.reserved_nano,op.user_id]);
    }
    if(!(await tx.get("SELECT id FROM paper_lint_credit_calls WHERE operation_id=? AND status='reserved' LIMIT 1",[operationId])))
      await tx.run("UPDATE paper_lint_credit_operations SET state='closed',finished_at=? WHERE id=?",[new Date().toISOString(),operationId]);
  });
}
async function recoverCreditOperations(){
  const rows=await all("SELECT o.*,j.status AS job_status FROM paper_lint_credit_operations o JOIN paper_lint_jobs j ON j.id=o.job_id WHERE o.state!='closed'");
  for(const op of rows){
    if(op.state==='active'&&op.job_status==='running'&&processAlive(op.owner_pid))continue;
    await finishCreditOperation(op.id);
  }
}
async function getAccountCredit(userId){
  for(const op of await all("SELECT o.id FROM paper_lint_credit_operations o JOIN paper_lint_jobs j ON j.id=o.job_id WHERE o.user_id=? AND o.state!='closed' AND (o.state='closing' OR j.status!='running' OR j.cancelled_at IS NOT NULL)",[userId]))await finishCreditOperation(op.id);
  const account=await get('SELECT * FROM paper_lint_credit_accounts WHERE user_id=?',[userId]);
  if(!account)throw Object.assign(new Error('未找到当前用户'),{status:404});
  const available=account.granted_nano-account.spent_nano-account.reserved_nano;
  return {user_id:account.user_id,currency:'CNY',policy_version:policy.version,granted_cny:money(account.granted_nano),spent_cny:money(account.spent_nano),
    reserved_cny:money(account.reserved_nano),available_cny:money(available),
    remaining_percent:account.granted_nano?Math.max(0,Math.min(100,available/account.granted_nano*100)):0,
    estimated_cny:policy.estimated_cny,server_time:new Date().toISOString()};
}
async function beginCreditOperation(jobId){
  return withTransaction(async tx=>{
    const job=await tx.get('SELECT * FROM paper_lint_jobs WHERE id=?',[jobId]);
    if(!job||job.status!=='running'||job.cancelled_at)throw Object.assign(new Error('Credit job is not running'),{code:'CREDIT_JOB_NOT_RUNNING'});
    const id=randomUUID();
    await tx.run(`INSERT INTO paper_lint_credit_operations(id,job_id,user_id,job_attempt,owner_pid,state,created_at)
      VALUES (?,?,?,?,?,'active',?)`,[id,job.id,job.user_id,job.attempts,process.pid,new Date().toISOString()]);
    return {database_file:getDbPath(),operation_id:id};
  });
}
module.exports={policy,BILLABLE_RULE_IDS,money,getAccountCredit,beginCreditOperation,finishCreditOperation,recoverCreditOperations};
