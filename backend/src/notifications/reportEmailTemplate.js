// Universal report-ready notification. Delivery is handled by the outbox service.
const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function reportEmail(report,recipient,settings,jobId){
 const filename=String(report.source_filename||'论文.pdf').replace(/[\u0000-\u001f\u007f]/g,' ');
 const reportHref=`${settings.origin}/reports/pdf/${encodeURIComponent(report.id)}`;
 const notification=['您的论文检测报告已生成，请点击下方按钮查看。','Your thesis report is ready. Use the button below to view it.'];
 const type='font-family:Arial,\'Microsoft YaHei\',\'PingFang SC\',sans-serif;font-size:16px;font-weight:400;line-height:28px;color:#273442;';
 const para=(text,space=16)=>`<p style="${type}margin:0 0 ${space}px">${text}</p>`;
 const sections=[0,1].map(i=>{
  const L=(zh,en)=>i?en:zh,system=L('智慧学位 AI 评阅辅助系统','Smart Degree · AI Review Assistant'),institution=L('上海交通大学研究生学位信息系统','Shanghai Jiao Tong University Graduate Degree Information System');
  const href=reportHref+'?lang='+L('zh','en');
  const title=L('论文检测报告已生成','Your thesis report is ready');
  const automatic=L('系统自动发送，请勿回复。','This is an automated email. Please do not reply.');
  const signoff=L('祝好！','Best regards,');
  const text=[title,'',L('您好！','Hello,'),notification[i],'',L('检测文件：','Document: ')+filename,'',L('查看检测报告：','View report: ')+href,'',signoff,system,institution,'',automatic].join('\n');
  const html=`<section id="${L('chinese','english')}" lang="${L('zh-CN','en')}">
   <h1 style="font-family:Arial,'Microsoft YaHei','PingFang SC',sans-serif;font-size:24px;font-weight:700;line-height:34px;color:#273442;margin:0 0 24px">${title}</h1>
   ${para(L('您好！','Hello,')+'<br>'+escapeHtml(notification[i]),20)}
   <p style="${type}margin:0 0 20px;overflow-wrap:anywhere;word-break:break-word">${L('检测文件：','Document: ')}${escapeHtml(filename)}</p>
   ${para(`<a href="${escapeHtml(href)}" style="display:inline-block;background:#96354a;border:1px solid #96354a;border-radius:4px;padding:11px 26px;color:#fff;text-decoration:none;font-family:Arial,'Microsoft YaHei',sans-serif;font-size:16px;font-weight:400;line-height:26px">${L('查看检测报告','View report')}</a>`,28)}
   ${para(signoff,4)}
   ${para(`${system}<br>${institution}`,20)}
   ${para(automatic,0)}
  </section>`;
  return {text,html};
 });
 return {from:{name:settings.fromName,address:settings.from},to:recipient,
  subject:`论文检测报告已生成 | Report ready | ${filename}`.replace(/[\u0000-\u001f\u007f]/g,' ').slice(0,200),
  messageId:`<report-${jobId}@${settings.from.split('@')[1]}>`,disableFileAccess:true,disableUrlAccess:true,
  text:sections[0].text+'\n\n'+'─'.repeat(36)+'\n\n'+sections[1].text,
  html:`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>论文检测报告 | Thesis report</title><style>@media only screen and (max-width:480px){.outer{padding:12px 0!important}.letter{padding:28px 22px!important}}</style></head><body style="margin:0;background:#edf0f3;${type}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td class="outer" align="center" style="padding:28px 14px"><table role="presentation" width="680" cellpadding="0" cellspacing="0" style="width:100%;max-width:680px;border-collapse:collapse;background:#fff;border:1px solid #dfe3e8;border-top:3px solid #96354a"><tr><td class="letter" style="padding:30px 44px;${type}">${sections[0].html}</td></tr><tr><td style="padding:0 44px"><hr style="border:0;border-top:1px solid #dfe3e8;margin:0"></td></tr><tr><td class="letter" style="padding:30px 44px;${type}">${sections[1].html}</td></tr></table></td></tr></table></body></html>`};
}
module.exports={reportEmail};
