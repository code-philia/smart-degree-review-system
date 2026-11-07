function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function cleanHeader(value) { return String(value ?? '').replace(/[\u0000-\u001f\u007f]/g,' ').slice(0,200); }

function reportEmail(report, recipient, settings, jobId) {
  const filename = cleanHeader(report.source_filename || '论文.pdf');
  const link = `${settings.origin}/reports/pdf/${encodeURIComponent(report.id)}`;
  const summary = report.summary;
  const counts = [ ['错误总数', summary.finding_count || 0], ['严重', summary.error_finding_count || 0],
    ['警告', summary.warning_finding_count || 0], ['提示', summary.info_finding_count || 0],
    ['未能完成检测', summary.execution_warning_count || 0] ];
  const date = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',dateStyle:'medium',timeStyle:'medium'}).format(new Date(report.created_at));
  const reasons = [...new Set((report.result?.rule_runs || [])
    .filter(rule => ['unsupported','error'].includes(rule.execution_status) || rule.outcome === 'inconclusive')
    .map(rule => rule.message).filter(Boolean))];
  const rejected = report.result?.document_validation?.status === 'rejected';
  const conclusion = rejected ? '该文件未通过论文检查，请登录查看具体原因。'
    : summary.execution_warning_count ? '报告已生成，部分规则未能完成检测，请结合报告说明查看结果。'
      : summary.finding_count ? '报告已生成，请登录查看检测问题与修改建议。' : '本次检测未发现可确认的问题。';
  const text = ['智慧学位 AI 评阅辅助系统','论文检测报告已生成',`文档名称：${filename}`,`完成时间：${date}（北京时间）`,conclusion,
    ...counts.map(([label,value]) => `${label}：${value}`), ...reasons, `查看检测报告：${link}`,
    '请使用提交该论文的账号登录后查看。检测结果仅供参考。','此邮件由系统自动发送，请勿直接回复。'].join('\n');
  const html = `<!doctype html><html lang="zh-CN"><body style="margin:0;background:#f3f6fb;font-family:Arial,'Microsoft YaHei',sans-serif;color:#20304a">
    <table role="presentation" style="width:100%;padding:32px 16px"><tr><td align="center"><table role="presentation" style="width:100%;max-width:600px;background:#fff;border:1px solid #dfe6ef;border-radius:16px;border-spacing:0;overflow:hidden">
    <tr><td style="padding:26px 30px;background:#16263e;color:#fff;font-size:17px;font-weight:600">智慧学位 AI 评阅辅助系统</td></tr>
    <tr><td style="padding:30px"><h1 style="margin:0 0 18px;font-size:24px;color:#172840">论文检测报告已生成</h1>
    <p style="font-size:15px;line-height:1.8;overflow-wrap:anywhere;margin:0 0 6px">${escapeHtml(filename)}</p>
    <p style="color:#64748b;font-size:13px;margin:0 0 24px">${escapeHtml(date)} · 北京时间</p>
    <p style="line-height:1.8;font-size:14px">${escapeHtml(conclusion)}</p>
    <table role="presentation" style="width:100%;border:1px solid #e5ebf3;border-radius:10px;background:#f8fafd;font-size:14px">${counts.map(([label,value])=>`<tr><td style="padding:9px 14px;color:#64748b">${label}</td><td style="padding:9px 14px;text-align:right;font-weight:600">${value}</td></tr>`).join('')}</table>
    ${reasons.length ? `<div style="margin-top:18px;font-size:13px;color:#64748b;line-height:1.8">${reasons.map(reason=>`<p>${escapeHtml(reason)}</p>`).join('')}</div>` : ''}
    <p style="margin:28px 0"><a href="${escapeHtml(link)}" style="display:inline-block;background:#3158bd;color:#fff;text-decoration:none;padding:13px 24px;border-radius:8px;font-weight:600;font-size:14px">查看检测报告 →</a></p>
    <p style="font-size:12px;line-height:1.8;color:#7a879b">请使用提交该论文的账号登录后查看。检测结果仅供参考。<br>此邮件由系统自动发送，请勿直接回复。</p></td></tr></table></td></tr></table></body></html>`;
  return { from:{name:settings.fromName,address:settings.from},to:recipient,subject:`论文检测已完成｜${filename}`,text,html,
    messageId:`<report-${jobId}@${settings.from.split('@')[1]}>`,disableFileAccess:true,disableUrlAccess:true };
}
module.exports = { reportEmail };
