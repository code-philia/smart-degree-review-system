const fs = require('fs/promises');
const path = require('path');
const { randomUUID } = require('crypto');
const db = require('../database/db_runtime');
const { getDbPath } = require('../database/init_db');

const REASONS = {
  false_positive: '误报', location_inaccurate: '位置不准确', description_unclear: '描述不清楚',
  incorrect: '建议不正确', not_directly_executable: '无法直接执行', insufficient_basis: '依据不足',
  unclear: '不清楚', other: '其他',
};
const AREAS = {
  detection_accuracy: '检测准确性', ai_suggestion_quality: 'AI建议质量', pdf_location: 'PDF定位',
  system_response_speed: '响应速度', system_stability: '稳定性', page_design: '界面设计', other: '其他',
};
const TYPES = { system: '使用反馈', finding: '检测结果评价', suggestion: '修复建议评价' };
const COLUMNS = [
  ['type_label','反馈类型'], ['username','账号'], ['display_name','姓名'], ['user_id','用户ID'], ['role','角色'],
  ['source_filename','检测文件'], ['report_id','报告ID'], ['rule_id','规则ID'], ['finding_id','结果ID'],
  ['suggestion_id','建议ID'], ['generation','建议版本'], ['feedback_label','评价'], ['reason_label','原因'],
  ['reason_text','原因说明'], ['satisfaction_score','满意度'], ['improvement_labels','改进方面'], ['comment','使用反馈说明'],
  ['created_at_beijing','创建时间（北京时间）'], ['updated_at_beijing','更新时间（北京时间）'], ['id','反馈ID'],
];

const COMMON = ['id','user_id','report_id','rule_id','finding_id','suggestion_id','generation',
  'feedback_value','reason_code','reason_text','satisfaction_score','improvement_areas_json','comment','created_at','updated_at'];
function query(type, table, fields) {
  return "SELECT '" + type + "' AS type," + COMMON.map(k => (fields[k] || 'NULL') + ' AS ' + k).join(',')
    + ',u.username,u.display_name,u.role,' + (type === 'system' ? 'NULL' : 'r.source_filename') + ' AS source_filename'
    + ' FROM ' + table + ' f LEFT JOIN auth_users u ON u.id=f.user_id'
    + (type === 'system' ? '' : ' LEFT JOIN paper_lint_reports r ON r.id=f.report_id');
}
function columns(names) { return Object.fromEntries(names.map(k=>[k,'f.'+k])); }
const SQL = [
  query('system','system_feedback', { ...columns(['id','user_id','satisfaction_score','improvement_areas_json','comment','created_at']), updated_at:'f.created_at' }),
  ...[['finding','paper_lint_finding_feedback'],['suggestion','paper_lint_suggestion_feedback']].map(([type,table]) =>
    query(type,table,columns(['id','user_id','report_id','rule_id','finding_id','feedback_value','reason_code','reason_text','created_at','updated_at',
      ...(type === 'suggestion' ? ['suggestion_id','generation'] : [])]))),
].join(' UNION ALL ') + ' ORDER BY created_at,id';

function beijing(value) {
  if (!value) return '';
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value.replace(' ','T')+'Z');
  if (!Number.isFinite(date.getTime())) return value;
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23' }).formatToParts(date).map(x=>[x.type,x.value]));
  return p.year+'-'+p.month+'-'+p.day+' '+p.hour+':'+p.minute+':'+p.second;
}
function csvCell(value) {
  let text = String(value == null ? '' : value);
  // CSV is for spreadsheet readers; JSON preserves the unmodified value.
  if (/^[\s\uFEFF]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
  return '"' + text.replace(/"/g,'""') + '"';
}
async function atomicWrite(dir, name, content) {
  const temp = path.join(dir, '.'+name+'.'+randomUUID()+'.tmp');
  try {
    await fs.writeFile(temp,content,{encoding:'utf8',mode:0o600,flag:'wx'});
    await fs.rename(temp,path.join(dir,name));
  } finally { await fs.unlink(temp).catch(error=>{ if (error.code !== 'ENOENT') throw error; }); }
}
let tail = Promise.resolve();
function refreshFeedbackArchive(options = {}) {
  const database = options.database || db;
  const dir = path.join(path.dirname(options.dbPath || getDbPath()),'feedback');
  const work = tail.catch(()=>{}).then(async () => {
    const rows = await database.all(SQL);
    const records = rows.map(row => {
      let areas = [];
      try { areas = JSON.parse(row.improvement_areas_json || '[]'); } catch {}
      if (!Array.isArray(areas)) areas = [];
      const { improvement_areas_json, ...record } = row;
      return { ...record, type_label:TYPES[row.type], feedback_label:row.feedback_value === 'positive' ? '点赞' : row.feedback_value === 'negative' ? '点踩' : '',
        reason_label:REASONS[row.reason_code] || row.reason_code || '', improvement_areas:areas,
        improvement_labels:areas.map(x=>AREAS[x] || x).join('；'),
        created_at_beijing:beijing(row.created_at), updated_at_beijing:beijing(row.updated_at) };
    });
    await fs.mkdir(dir,{recursive:true,mode:0o700});
    await fs.chmod(dir,0o700);
    const snapshot = {schema_version:1,generated_at:new Date().toISOString(),records};
    await atomicWrite(dir,'feedback.json',JSON.stringify(snapshot,null,2)+'\n');
    await atomicWrite(dir,'feedback.csv','\uFEFF'+[COLUMNS.map(c=>csvCell(c[1])).join(','),...records.map(r=>COLUMNS.map(c=>csvCell(r[c[0]])).join(','))].join('\r\n')+'\r\n');
    return {directory:dir,count:records.length};
  });
  tail = work;
  return work;
}
async function refreshFeedbackArchiveSafely() {
  try { return await refreshFeedbackArchive(); }
  catch (error) { console.error('Feedback archive refresh failed:', error.code || error.name); return null; }
}
module.exports = { refreshFeedbackArchive, refreshFeedbackArchiveSafely };
