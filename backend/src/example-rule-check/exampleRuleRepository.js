const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { all, get, run } = require('../database');

const root = () => path.resolve(process.env.EXAMPLE_RULE_REPORTS_DIR || path.join(process.cwd(), 'data', 'example-rule-check'));
const parse = (value, fallback) => { try { return JSON.parse(value); } catch { return fallback; } };
const now = () => new Date().toISOString();

function doc(row) { return row && { id: row.id, source_filename: row.source_filename, annotations: parse(row.annotations_json, []), created_at: row.created_at, updated_at: row.updated_at }; }
function rule(row) { return row && { id: row.id, name: row.name, intent: row.intent, status: row.status, version: row.version, definition: parse(row.rule_json, {}), created_at: row.created_at, updated_at: row.updated_at }; }
function report(row, details = true) { return row && { id: row.id, source_filename: row.source_filename, rule_snapshots: parse(row.rule_snapshots_json, []), ...(details ? { result: parse(row.result_json, {}) } : { summary: parse(row.result_json, {}).summary || {} }), created_at: row.created_at }; }

async function storePdf(kind, id, buffer) {
  const directory = path.join(root(), kind);
  await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
  const filePath = path.join(directory, `${id}.pdf`);
  await fs.promises.writeFile(filePath, buffer, { flag: 'wx', mode: 0o600 });
  return filePath;
}
async function createDocument(userId, sourceFilename, buffer) {
  const id = randomUUID(); const pdfPath = await storePdf('examples', id, buffer); const timestamp = now();
  try { await run('INSERT INTO example_rule_documents (id,user_id,source_filename,source_pdf_path,annotations_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)', [id,userId,sourceFilename,pdfPath,'[]',timestamp,timestamp]); }
  catch (error) { await fs.promises.rm(pdfPath, { force: true }); throw error; }
  return findDocument(userId, id);
}
async function listDocuments(userId) { return (await all('SELECT * FROM example_rule_documents WHERE user_id=? ORDER BY created_at DESC', [userId])).map(doc); }
async function findDocument(userId, id) { return doc(await get('SELECT * FROM example_rule_documents WHERE id=? AND user_id=?', [id,userId])); }
async function updateDocumentAnnotations(userId,id,annotations) { await run('UPDATE example_rule_documents SET annotations_json=?,updated_at=? WHERE id=? AND user_id=?', [JSON.stringify(annotations),now(),id,userId]); return findDocument(userId,id); }
async function readDocumentPdf(userId,id) { const row=await get('SELECT source_filename,source_pdf_path FROM example_rule_documents WHERE id=? AND user_id=?',[id,userId]); if(!row)return null; try{return {source_filename:row.source_filename,content:await fs.promises.readFile(row.source_pdf_path)}}catch(error){if(error.code==='ENOENT')return {...row,content:null};throw error;} }
async function createRule(userId, input) { const id=randomUUID(), timestamp=now(), snapshot=JSON.stringify(input.definition); await run('INSERT INTO example_rule_definitions (id,user_id,name,intent,status,version,rule_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',[id,userId,input.name,input.intent,input.status,1,snapshot,timestamp,timestamp]); await run('INSERT INTO example_rule_versions (id,rule_id,user_id,version,rule_snapshot_json,created_at) VALUES (?,?,?,?,?,?)',[randomUUID(),id,userId,1,snapshot,timestamp]); return findRule(userId,id); }
async function listRules(userId) { return (await all('SELECT * FROM example_rule_definitions WHERE user_id=? ORDER BY updated_at DESC',[userId])).map(rule); }
async function findRule(userId,id) { return rule(await get('SELECT * FROM example_rule_definitions WHERE id=? AND user_id=?',[id,userId])); }
async function updateRule(userId,id,input) { const existing=await findRule(userId,id); if(!existing)return null; const version=existing.version+1,timestamp=now(),snapshot=JSON.stringify(input.definition); await run('UPDATE example_rule_definitions SET name=?,intent=?,status=?,version=?,rule_json=?,updated_at=? WHERE id=? AND user_id=?',[input.name,input.intent,input.status,version,snapshot,timestamp,id,userId]); await run('INSERT INTO example_rule_versions (id,rule_id,user_id,version,rule_snapshot_json,created_at) VALUES (?,?,?,?,?,?)',[randomUUID(),id,userId,version,snapshot,timestamp]); return findRule(userId,id); }
async function deleteRule(userId,id) { return (await run('DELETE FROM example_rule_definitions WHERE id=? AND user_id=?',[id,userId])).changes > 0; }
async function createReport(userId,sourceFilename,buffer,snapshots,result) { const id=randomUUID(),timestamp=now(),pdfPath=await storePdf('reports',id,buffer); try { await run('INSERT INTO example_rule_reports (id,user_id,source_filename,source_pdf_path,rule_snapshots_json,result_json,created_at) VALUES (?,?,?,?,?,?,?)',[id,userId,sourceFilename,pdfPath,JSON.stringify(snapshots),JSON.stringify(result),timestamp]); } catch(error){await fs.promises.rm(pdfPath,{force:true});throw error;} return findReport(userId,id); }
async function listReports(userId) { return (await all('SELECT * FROM example_rule_reports WHERE user_id=? ORDER BY created_at DESC',[userId])).map((row)=>report(row,false)); }
async function findReport(userId,id) { return report(await get('SELECT * FROM example_rule_reports WHERE id=? AND user_id=?',[id,userId])); }
async function readReportPdf(userId,id) { const row=await get('SELECT source_filename,source_pdf_path FROM example_rule_reports WHERE id=? AND user_id=?',[id,userId]); if(!row)return null; try{return {source_filename:row.source_filename,content:await fs.promises.readFile(row.source_pdf_path)}}catch(error){if(error.code==='ENOENT')return {...row,content:null};throw error;} }
module.exports={createDocument,listDocuments,findDocument,updateDocumentAnnotations,readDocumentPdf,createRule,listRules,findRule,updateRule,deleteRule,createReport,listReports,findReport,readReportPdf};
