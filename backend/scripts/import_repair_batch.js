// Validates every input before writing; repeated imports reuse verified rows.
const fs = require('fs/promises');
const path = require('path');
const db = require('../src/database/db_runtime');
const service = require('../src/normative/repairSuggestionService');
const { sha256 } = require('../src/normative/legacyRepairAdapter');
const { buildArchiveRepairRequestWithPdfContext, resolveArchivePdfPath } = require('../src/normative/repairEvidenceService');
const { PROMPT_VERSION, getRepairModelIdentity } = require('../src/normative/repairModelProposalService');
const { verifyBatchRepairRecord } = require('../src/normative/repairBatchImport');
async function run() {
  const args=process.argv.slice(2);
  const value=flag=>args[args.indexOf(flag)+1];
  if (!args.includes('--input') || !args.includes('--audit-dir')) throw new Error('Required: --input batch.json --audit-dir private-directory [--apply]');
  const input=value('--input'), audit=value('--audit-dir'), apply=args.includes('--apply');
  const content=await fs.readFile(input); const batchSha256=sha256(content); const batch=JSON.parse(content);
  if (batch.schema_version!=='repair-batch-v1' || !Array.isArray(batch.records)) throw new Error('Unsupported repair batch');
  const identity=await getRepairModelIdentity();
  if (batch.model!==identity.model || batch.model_version!==identity.modelVersion || batch.prompt_version!==PROMPT_VERSION) throw new Error('Batch model/prompt differs from the current runtime');
  await fs.mkdir(audit,{recursive:true,mode:0o700});
  const prepared=[], skipped=[], errors=[], hashes=new Map(), ids=new Set(); let existing=0;
  for (const record of batch.records) {
    const source=record.source || {}; const key=JSON.stringify([source.jobId,source.documentId,source.ruleId,source.findingId]);
    try {
      if (ids.has(key)) throw new Error('Duplicate finding identity'); ids.add(key);
      let current;
      try { current=await service.getArchiveFinding(source.jobId,source.documentId,source.ruleId,source.findingId); }
      catch (error) {
        if (error.status!==404) throw error;
        const row=await db.get('SELECT result_json FROM archive_scan_documents WHERE job_id=? AND id=?',[source.jobId,source.documentId]);
        const result=row?.result_json ? JSON.parse(row.result_json) : null;
        const dismissed=result?.finding_reviews?.some(review=>review.rule_id===source.ruleId && review.finding_id===source.findingId && review.disposition==='false_positive');
        if (!dismissed) throw error;
        skipped.push({source,reason:'user-confirmed false positive already dismissed'}); continue;
      }
      const request=await buildArchiveRepairRequestWithPdfContext(source);
      const pdf=await resolveArchivePdfPath(current.document.relative_path);
      if (!hashes.has(pdf)) hashes.set(pdf,sha256(await fs.readFile(pdf)));
      const response=verifyBatchRepairRecord(record,request,{document:current.document,pdfSha256:hashes.get(pdf),batchSha256,inputName:path.basename(input),...identity});
      const cached=await service.findRepairSuggestion(request,{model:identity.model,modelVersion:identity.modelVersion,promptVersion:PROMPT_VERSION});
      if (cached?.provenance.import_batch_sha256===batchSha256 && cached.provenance.source_identity_sha256===request.source_identity_sha256) {existing++;continue;}
      prepared.push({source,request,response});
    } catch (error) {errors.push({source,error:error.message});}
  }
  const summary={input,batch_sha256:batchSha256,selected:batch.records.length,prepared:prepared.length,existing,skipped,errors,verified_pdfs:hashes.size,apply};
  await fs.writeFile(path.join(audit,'import-validation.json'),JSON.stringify(summary,null,2));
  console.log(JSON.stringify({...summary,errors:errors.slice(0,5),error_count:errors.length}));
  if (errors.length) throw new Error('Batch verification failed; no records imported');
  if (!apply) return;
  if (sha256(await fs.readFile(input))!==batchSha256) throw new Error('Batch file changed during validation');
  for (const [index, entry] of prepared.entries()) {
    const current=await service.buildArchiveRepairRequest(entry.source);
    if (current.source_identity_sha256!==entry.request.source_identity_sha256) throw new Error('Finding changed after validation');
    await service.saveRepairSuggestion(entry.request,entry.response);
    if ((index+1)%100===0) console.log(JSON.stringify({saved:index+1,total:prepared.length}));
  }
  await fs.writeFile(path.join(audit,'import-complete.json'),JSON.stringify({inserted:prepared.length,existing,skipped,verified_pdfs:hashes.size,batch_sha256:batchSha256},null,2));
}
if (require.main === module) run().catch(error=>{console.error(error.message);process.exitCode=1;})
  .finally(()=>require('../src/database/init_db').closeDb());
