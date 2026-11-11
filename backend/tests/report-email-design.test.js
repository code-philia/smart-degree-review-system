import {expect,it} from 'vitest';
import {createRequire} from 'node:module';
const {reportEmail}=createRequire(import.meta.url)('../src/notifications/reportEmailTemplate');
const settings={origin:'https://review.example.test',from:'sender@sjtu.edu.cn',fromName:'智慧学位'};
const base={id:'report-1',source_filename:'学位论文_清晰完整的检测文件名.pdf',created_at:'2026-11-11T08:30:00Z',summary:{finding_count:4,error_finding_count:1,warning_finding_count:2,info_finding_count:1,execution_warning_count:0},result:{rule_runs:[]}};
it('puts complete Chinese and English letters in order, with one language-specific action in each',()=>{
 const mail=reportEmail(base,'reader@example.test',settings,'job1');
 const chinese=mail.html.match(/<section[^>]*id="chinese"[^>]*>([\s\S]*?)<\/section>/)?.[1];
 const english=mail.html.match(/<section[^>]*id="english"[^>]*>([\s\S]*?)<\/section>/)?.[1];
 expect(chinese).toContain('祝好');expect(chinese).toContain('智慧学位 AI 评阅辅助系统');
 expect(chinese).toContain('上海交通大学研究生学位信息系统');expect(chinese).not.toContain('Best regards');
 expect(english).toContain('Best regards');expect(english).toContain('Smart Degree · AI Review Assistant');
 expect(english).toContain('Shanghai Jiao Tong University Graduate Degree Information System');
 expect(mail.html.indexOf('id="chinese"')).toBeLessThan(mail.html.indexOf('id="english"'));
 expect(mail.text.indexOf('上海交通大学研究生学位信息系统')).toBeLessThan(mail.text.indexOf('Hello,'));
 expect(chinese.match(/<a /g)).toHaveLength(1);expect(english.match(/<a /g)).toHaveLength(1);
 for(const [section,lang] of [[chinese,'zh'],[english,'en']])expect(section).toContain('href="https://review.example.test/reports/pdf/report-1?lang='+lang+'"');
 expect(mail.text).toContain('https://review.example.test/reports/pdf/report-1?lang=zh');
 expect(mail.text).toContain('https://review.example.test/reports/pdf/report-1?lang=en');
 expect(mail.html).not.toMatch(/<select|<script|<img|Registry Office|教务处/);
 expect(mail.attachments).toBeUndefined();expect(mail.messageId).toBe('<report-job1@sjtu.edu.cn>');
 expect(mail.disableFileAccess).toBe(true);expect(mail.disableUrlAccess).toBe(true);
});
it.each([
 {summary:{finding_count:0}},
 {summary:{finding_count:0,error_rule_count:2}},
 {summary:{finding_count:0,unsupported_rule_count:2}},
 {summary:{finding_count:9,execution_warning_count:2}},
 {result:{document_validation:{status:'rejected'}}},
 {summary:undefined},
])('uses the same report-ready notice for every result and execution status (%j)',patch=>{
 const mail=reportEmail({...base,...patch},'reader@example.test',settings,'job2');
 const ordinary=reportEmail(base,'reader@example.test',settings,'job2');
 expect(mail.text).toBe(ordinary.text);expect(mail.html).toBe(ordinary.html);
 expect(mail.text).toContain('您的论文检测报告已生成');expect(mail.text).toContain('Your thesis report is ready.');
 expect(mail.text).not.toMatch(/问题总数|完成时间|严重|警告|Critical|Warnings|Completed:|No confirmed findings|检测已完成|请使用提交|Results are for reference|Sign in with/);
});
it('retains the complete escaped filename and bounds the header without control characters',()=>{
 const filename='论文'.repeat(160)+'<script>\r\nInjected';
 const mail=reportEmail({...base,source_filename:filename,id:'report #1'},'reader@example.test',settings,'job3');
 expect(mail.subject.length).toBeLessThanOrEqual(200);expect(mail.subject).not.toMatch(/[\r\n]/);
 expect(mail.html).not.toContain('<script>');expect(mail.html).toContain('论文'.repeat(160)+'&lt;script&gt;  Injected');
 expect(mail.html).toContain('/reports/pdf/report%20%231?lang=zh');
 expect(mail.html).toContain('/reports/pdf/report%20%231?lang=en');
});
