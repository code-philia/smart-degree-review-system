const express=require('express');
const {requireAuth}=require('../auth/authMiddleware');
const repository=require('./paperLintReportRepository');
const {renderReport,MAX_MODEL_BYTES}=require('./reportExportService');
function createReportExportRouter({getReport=repository.findPaperLintReportByIdForUser,generate=renderReport}={}) {
  const router=express.Router();
  router.post('/reports/:reportId/export',requireAuth({allowedRoles:['STUDENT','SUPERVISOR','SCHOOL_ADMIN','COLLEGE_ADMIN']}),express.json({limit:MAX_MODEL_BYTES+1024}),async(req,res,next)=>{
    const controller=new AbortController();
    const cancel=()=>{if(!res.writableEnded)controller.abort();};res.once('close',cancel);
    try {
      const report=await getReport(req.params.reportId,req.user.id);
      if(!report)return res.status(404).json({code:404,message:'未找到该审查报告'});
      if(!req.body || !['pdf','image'].includes(req.body.format))return res.status(400).json({code:400,message:'请选择有效导出格式。'});
      const output=await generate({userId:req.user.id,report,model:req.body.model,format:req.body.format,signal:controller.signal});
      if(controller.signal.aborted)return;
      res.set('Cache-Control','private, no-store');res.set('X-Content-Type-Options','nosniff');
      res.type(output.contentType);res.attachment(output.filename);return res.send(output.content);
    }catch(error){
      if(error.name==='AbortError' || controller.signal.aborted)return;
      if(error.status)return res.status(error.status).json({code:error.status,message:error.message});
      return next(error);
    }finally{res.removeListener('close',cancel);}
  });
  return router;
}
module.exports={createReportExportRouter};
