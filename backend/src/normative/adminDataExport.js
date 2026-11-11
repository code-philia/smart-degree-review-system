// Local maintenance tool only. Never register this module as an HTTP route.
const fs = require('fs/promises');
const { createReadStream } = require('fs');
const path = require('path');
const { createHash, randomUUID } = require('crypto');
const db = require('../database/db_runtime');
const { getDbPath } = require('../database/init_db');
function reportsDirectory() {
  return path.resolve(process.env.PAPER_LINT_REPORTS_DIR || path.join(process.cwd(),'data','paper-lint-reports'));
}

async function hashFile(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
function csv(value) {
  let s=String(value == null ? '' : value);
  if (/^[\s\uFEFF]*[=+\-@]/.test(s) || /^[\t\r\n]/.test(s)) s="'"+s;
  return '"'+s.replace(/"/g,'""')+'"';
}
function plain(value) { return String(value == null ? '' : value).replace(/[<>]/g,c=>c==='<'?'&lt;':'&gt;').replace(/[\r\n]+/g,' '); }
function readable(row, result) {
  const lines=['# 检测报告 / Review report','',
    '文件 / Document: '+plain(row.source_filename),
    '用户 / User: '+plain(row.username)+' ('+plain(row.user_id)+')',
    '时间 / Created: '+plain(row.created_at),'',
    '以下为已保存报告的维护用文字副本，原始结构与字段见同目录 report.json。',''];
  for (const run of result.rule_runs || []) {
    lines.push('## '+plain(run.title || run.rule_id),'',
      '执行状态 / Status: '+plain(run.execution_status || run.status || 'unspecified'),'');
    if (run.message) lines.push(plain(run.message),'');
    for (const [i,f] of (run.findings || []).entries()) {
      lines.push('### '+(i+1)+'. '+plain(f.severity || run.severity || 'unspecified'),'',
        plain(f.message || f.description || f.title || ''),'');
      if (f.location) lines.push('位置 / Location: '+JSON.stringify(f.location),'');
      if (f.suggestion) lines.push('建议 / Suggestion: '+plain(typeof f.suggestion === 'string' ? f.suggestion : JSON.stringify(f.suggestion)),'');
    }
  }
  return lines.join('\n')+'\n';
}
async function exportAllReports(options={}) {
  const database=options.database || db;
  const base=path.join(path.dirname(options.dbPath || getDbPath()),'admin-export');
  const uploadsPaths=[options.uploadsDir || reportsDirectory(),...(process.env.ADMIN_EXPORT_PDF_ROOTS || '').split(path.delimiter).filter(Boolean)];
  const uploadsRoots=await Promise.all(uploadsPaths.map(p=>fs.realpath(p).catch(error=>{if(error.code==='ENOENT')return path.resolve(p);throw error;})));
  await fs.mkdir(base,{recursive:true,mode:0o700});await fs.chmod(base,0o700);
  const directory=await fs.mkdtemp(path.join(base,'snapshot-'));
  const records=[];
  const rows=await database.all('SELECT r.*,u.username,u.display_name,u.role FROM paper_lint_reports r LEFT JOIN auth_users u ON u.id=r.user_id ORDER BY r.created_at,r.id');
  try {
    for (const [i,row] of rows.entries()) {
      const name=String(i+1).padStart(6,'0');
      const dir=path.join(directory,name);await fs.mkdir(dir,{mode:0o700});
      const result=JSON.parse(row.result_json);
      const report={id:row.id,user_id:row.user_id,username:row.username,display_name:row.display_name,role:row.role,
        source_filename:row.source_filename,created_at:row.created_at,selected_rule_ids:JSON.parse(row.selected_rule_ids_json || '[]'),result};
      await fs.writeFile(path.join(dir,'report.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});
      await fs.writeFile(path.join(dir,'report.md'),readable(row,result),{mode:0o600});
      const record={report_id:row.id,user_id:row.user_id,username:row.username,display_name:row.display_name,role:row.role,source_filename:row.source_filename,created_at:row.created_at,
        report_file:name+'/report.json',readable_file:name+'/report.md',pdf_file:null,pdf_status:'not_copied',pdf_sha256:null};
      if (!options.indexOnly) {
        try {
          const source=await fs.realpath(row.source_pdf_path);
          const allowed=uploadsRoots.some(root=>{const relative=path.relative(root,source);return relative && relative!=='..' && !relative.startsWith('..'+path.sep) && !path.isAbsolute(relative);});
          if (!allowed) record.pdf_status='outside_upload_root';
          else if (!(await fs.stat(source)).isFile()) record.pdf_status='not_regular_file';
          else {
            const target=path.join(dir,'source.pdf');
            await fs.copyFile(source,target);await fs.chmod(target,0o600);
            record.pdf_file=name+'/source.pdf';record.pdf_status='copied';record.pdf_sha256=await hashFile(target);
          }
        } catch(error) { if(error.code==='ENOENT') record.pdf_status='missing'; else throw error; }
      }
      records.push(record);
    }
    const summary={schema_version:1,generated_at:new Date().toISOString(),report_count:records.length,pdf_count:records.filter(x=>x.pdf_status==='copied').length,index_only:Boolean(options.indexOnly)};
    await fs.writeFile(path.join(directory,'index.json'),JSON.stringify({...summary,records},null,2)+'\n',{mode:0o600});
    const keys=['username','display_name','user_id','role','source_filename','created_at','report_id','report_file','readable_file','pdf_file','pdf_status','pdf_sha256'];
    await fs.writeFile(path.join(directory,'index.csv'),'\uFEFF'+[keys.map(csv).join(','),...records.map(r=>keys.map(k=>csv(r[k])).join(','))].join('\r\n')+'\r\n',{mode:0o600});
    const temp=path.join(base,'.latest-'+randomUUID()+'.tmp');
    try {
      await fs.writeFile(temp,JSON.stringify({...summary,snapshot:path.basename(directory)},null,2)+'\n',{mode:0o600,flag:'wx'});
      await fs.rename(temp,path.join(base,'latest.json'));
    } finally {await fs.unlink(temp).catch(e=>{if(e.code!=='ENOENT')throw e;});}
    return {...summary,directory};
  } catch(error) {
    await fs.rm(directory,{recursive:true,force:true});
    throw error;
  }
}
module.exports={exportAllReports};
