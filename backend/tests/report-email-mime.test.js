import {expect,it,afterEach} from 'vitest';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const nodemailer=require('nodemailer');
const {reportEmail}=require('../src/notifications/reportEmailTemplate');
const {mailConfig}=require('../src/notifications/mailConfig');
const keys=['REPORT_EMAIL_ENABLED','SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_PORT','SMTP_FROM_ADDRESS','APP_PUBLIC_URL'];
const original=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
afterEach(()=>{for(const [key,value] of Object.entries(original)){if(value===undefined)delete process.env[key];else process.env[key]=value;}});
it('serializes a Chinese report email as HTML and plain text without network or attachments',async()=>{
  const mail=reportEmail({id:'1234',source_filename:'学位论文.pdf',created_at:'2026-11-07T00:00:00Z',summary:{finding_count:0},result:{rule_runs:[]}},'recipient@example.test',
    {origin:'https://review.example.test',from:'sender@example.test',fromName:'学位系统'},'1234');
  const result=await nodemailer.createTransport({streamTransport:true,buffer:true}).sendMail(mail);
  const source=result.message.toString();
  expect(source).toContain('multipart/alternative');expect(source).toContain('text/plain');expect(source).toContain('text/html');
  expect(source).toContain('To: recipient@example.test');expect(source).toContain('Message-ID: <report-1234@example.test>');
  expect(source).not.toContain('application/pdf');expect(source).not.toContain('Content-Disposition: attachment');
});
it('requires explicit sender authorization and a trusted configured report origin',()=>{
  Object.assign(process.env,{REPORT_EMAIL_ENABLED:'1',SMTP_HOST:'mail.sjtu.edu.cn',SMTP_PORT:'465',SMTP_USER:'gs.xwb1@sjtu.edu.cn',SMTP_PASSWORD:'test-only',APP_PUBLIC_URL:'https://review.example.test'});
  expect(mailConfig()).toMatchObject({port:465,origin:'https://review.example.test'});
  process.env.APP_PUBLIC_URL='https://user:pass@evil.example/path';expect(mailConfig()).toBeNull();
  process.env.APP_PUBLIC_URL='https://review.example.test';delete process.env.SMTP_PASSWORD;expect(mailConfig()).toBeNull();
});
