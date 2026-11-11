// One report-ready letter in the language captured by the submitting interface.
// Delivery, retries and cancellation remain the outbox service's responsibility.
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
const family = "Arial,'Microsoft YaHei','PingFang SC',sans-serif";
const type = `font-family:${family};font-size:16px;font-weight:400;line-height:24px;color:#334155;`;
const paragraph = text => `<p style="margin:0;${type}">${text}</p>`;
const row = (html, padding = 0) => `<tr><td style="padding:0 0 ${padding}px;${type}">${html}</td></tr>`;

function reportEmail(report, recipient, settings, jobId, locale = 'zh') {
  const language = locale === 'en' ? 'en' : 'zh';
  const L = (zh, en) => language === 'en' ? en : zh;
  const filename = String(report.source_filename || L('论文.pdf', 'thesis.pdf')).replace(/[\u0000-\u001f\u007f]/g, ' ');
  const href = `${settings.origin}/reports/pdf/${encodeURIComponent(report.id)}?lang=${language}`;
  const title = L('论文检测报告已生成', 'Your thesis report is ready');
  const greeting = L('您好！', 'Hello,');
  const ready = L('您的论文检测报告已生成。', 'Your thesis report is ready.');
  const action = L('查看检测报告', 'View report');
  const automatic = L('系统自动发送，请勿回复。', 'This is an automated email. Please do not reply.');
  const button = `<table role="presentation" class="action" width="196" cellpadding="0" cellspacing="0" border="0" style="width:196px;max-width:100%;border-collapse:separate"><tr><td align="center" bgcolor="#96354a" style="background:#96354a;border:1px solid #96354a;border-radius:5px;mso-padding-alt:12px 16px"><a href="${escapeHtml(href)}" style="display:block;padding:11px 16px;${type}color:#ffffff;line-height:24px;text-align:center;text-decoration:none!important;mso-padding-alt:0"><span style="color:#ffffff;text-decoration:none!important">${action}</span></a></td></tr></table>`;
  const body =
    row(`<h1 style="margin:0;font-family:${family};font-size:20px;font-weight:600;line-height:28px;color:#1f2937">${title}</h1>`, 16) +
    row(paragraph(`${greeting}<br>${ready}`), 16) +
    row(`<p style="margin:0;${type}color:#64748b">${L('检测文件', 'Document')}</p><p data-filename="" style="margin:0;${type}overflow-wrap:anywhere;word-wrap:break-word;word-break:break-word">${escapeHtml(filename)}</p>`, 16) +
    row(button, 16) +
    row(`<p style="margin:0;${type}color:#64748b">${automatic}</p>`);

  return {
    from: { name: settings.fromName, address: settings.from }, to: recipient,
    subject: `${L('【智慧学位 AI 评阅辅助系统】', '[Smart Degree · AI Review Assistant] ')}${title} | ${filename}`.slice(0, 200),
    messageId: `<report-${jobId}@${settings.from.split('@')[1]}>`,
    disableFileAccess: true, disableUrlAccess: true,
    text: [title, '', greeting, ready, '', L('检测文件：', 'Document: ') + filename, '', `${action}: ${href}`, '', automatic].join('\n'),
    html: `<!doctype html><html lang="${L('zh-CN', 'en')}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="format-detection" content="telephone=no,date=no,address=no,email=no"><title>${title}</title><style>body,table,td,p,a{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}table{mso-table-lspace:0;mso-table-rspace:0}a{text-decoration:none}@media only screen and (max-width:480px){.outer{padding:0!important}.letter{padding:24px 20px!important}.action{width:100%!important}}</style></head><body style="margin:0;padding:0;background:#ffffff;${type}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#ffffff"><tr><td class="outer" align="center" style="padding:24px 16px"><!--[if mso]><table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]--><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:640px;table-layout:fixed;border-collapse:collapse;border-top:2px solid #96354a"><tr><td class="letter" style="padding:28px 32px;${type}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;table-layout:fixed;border-collapse:collapse">${body}</table></td></tr></table><!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>`,
  };
}
module.exports = { reportEmail };
