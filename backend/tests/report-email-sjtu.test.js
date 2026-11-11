import {beforeEach,afterEach,expect,it} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
const require=createRequire(import.meta.url);
const {mailConfig}=require('../src/notifications/mailConfig');
const keys=['REPORT_EMAIL_ENABLED','REPORT_EMAIL_PROVIDER','REPORT_EMAIL_NOT_BEFORE','APP_PUBLIC_URL','JACCOUNT_CLIENT_ID','JACCOUNT_CLIENT_SECRET','JACCOUNT_NOTIFICATION_USERNAME','JACCOUNT_NOTIFICATION_PASSWORD','JACCOUNT_NOTIFICATION_PASSWORD_FILE'];
let original,dir;
const settings={provider:'sjtu-notification',origin:'https://review.example.test',from:'gs.xwb1@sjtu.edu.cn',fromName:'研究生学位信息系统',clientId:'app-test',clientSecret:'application-test-secret',username:'gs.xwb1',password:'sender-test-secret'};
const id='11111111-2222-4333-8444-555555555555';
const mail={to:'123090058@link.cuhk.edu.cn',subject:'Report ready | thesis.pdf',text:'Summary and authenticated report link',html:'<p>Summary and report link</p>',messageId:`<report-${id}@sjtu.edu.cn>`};
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
const token=()=>json({access_token:'private-test-token',token_type:'Bearer',expires_in:1800});
const receipt=()=>json({errno:0,error:'success',total:0,entities:[{id,name:mail.subject,emails:[mail.to],channels:['email']}]});
function sender(request,now=()=>100000){return require('../src/notifications/sjtuNotificationSender').createSjtuNotificationSender({request,now});}
beforeEach(()=>{original=Object.fromEntries(keys.map(k=>[k,process.env[k]]));for(const k of keys)delete process.env[k];dir=fs.mkdtempSync(path.join(os.tmpdir(),'sjtu-mail-'));});
afterEach(()=>{for(const[k,v]of Object.entries(original)){if(v===undefined)delete process.env[k];else process.env[k]=v;}fs.rmSync(dir,{recursive:true,force:true});});
function configure(){Object.assign(process.env,{REPORT_EMAIL_ENABLED:'1',REPORT_EMAIL_PROVIDER:'sjtu-notification',APP_PUBLIC_URL:settings.origin,JACCOUNT_CLIENT_ID:settings.clientId,JACCOUNT_CLIENT_SECRET:settings.clientSecret,JACCOUNT_NOTIFICATION_USERNAME:settings.username});const file=path.join(dir,'sender.secret');fs.writeFileSync(file,settings.password+'\n',{mode:0o600});process.env.JACCOUNT_NOTIFICATION_PASSWORD_FILE=file;}
it('enables the API provider with private-file credentials without requiring SMTP',()=>{configure();expect(mailConfig()).toMatchObject(settings);});
it.each([['REPORT_EMAIL_PROVIDER','unknown'],['JACCOUNT_CLIENT_SECRET',''],['JACCOUNT_NOTIFICATION_USERNAME','invalid@account'],['APP_PUBLIC_URL','https://user:pass@evil.example/x'],['REPORT_EMAIL_NOT_BEFORE','not-a-date']])('fails closed for invalid %s', (key,value)=>{configure();process.env[key]=value;expect(mailConfig()).toBeNull();});
it('does not enable delivery for an unreadable sender password file',()=>{configure();process.env.JACCOUNT_NOTIFICATION_PASSWORD_FILE=path.join(dir,'missing');expect(mailConfig()).toBeNull();});
it('passes a valid cutover through to the worker',()=>{configure();process.env.REPORT_EMAIL_NOT_BEFORE='2026-11-11T08:00:00.000Z';expect(mailConfig()?.notBefore).toBe('2026-11-11T08:00:00.000Z');});
it('supports fixed campus SMTP using only the sender credentials without legacy SMTP settings',()=>{configure();process.env.REPORT_EMAIL_PROVIDER='sjtu-smtp';delete process.env.JACCOUNT_CLIENT_ID;delete process.env.JACCOUNT_CLIENT_SECRET;expect(mailConfig()).toMatchObject({provider:'sjtu-smtp',host:'mail.sjtu.edu.cn',port:465,user:'gs.xwb1@sjtu.edu.cn',from:'gs.xwb1@sjtu.edu.cn',password:'sender-test-secret'});});
it('does not enable fixed campus SMTP without its private sender credential',()=>{configure();process.env.REPORT_EMAIL_PROVIDER='sjtu-smtp';delete process.env.JACCOUNT_NOTIFICATION_PASSWORD_FILE;expect(mailConfig()).toBeNull();});
it('exchanges the sender password for a scoped token and submits the existing message over authenticated HTTPS',async()=>{
  const calls=[];const send=sender(async(url,opts)=>{calls.push({url,opts});return calls.length===1?token():receipt();});
  expect(await send(mail,settings)).toEqual({notificationId:id});expect(calls).toHaveLength(2);
  expect(calls[0].url).toBe('https://jaccount.sjtu.edu.cn/oauth2/token');expect(calls[0].opts.method).toBe('POST');
  const form=new URLSearchParams(calls[0].opts.body);expect(Object.fromEntries(form)).toEqual({grant_type:'password',scope:'send_notification',username:'gs.xwb1',password:'sender-test-secret'});
  expect(calls[0].opts.headers.Authorization).toBe('Basic '+Buffer.from('app-test:application-test-secret').toString('base64'));
  expect(calls[1].url).toBe('https://api.sjtu.edu.cn/v1/notification');expect(calls[1].opts.method).toBe('PUT');
  expect(calls[1].opts.headers.Authorization).toBe('Bearer private-test-token');
  expect(JSON.parse(calls[1].opts.body)).toEqual({id,name:mail.subject,content:mail.text,html:mail.html,emails:[mail.to],channels:['email']});
  for(const call of calls){expect(call.opts.redirect).toBe('error');expect(call.opts.signal).toBeTruthy();expect(call.url).not.toContain('private-test-token');}
});
it('shares one token across simultaneous deliveries and renews before expiration',async()=>{
  let now=100000,grants=0,deliveries=0;const send=sender(async url=>{if(url.endsWith('/token')){grants++;return token();}deliveries++;return receipt();},()=>now);
  await Promise.all([send(mail,settings),send(mail,settings),send(mail,settings)]);expect(grants).toBe(1);expect(deliveries).toBe(3);
  now+=1800000;await send(mail,settings);expect(grants).toBe(2);
});
it('never reuses a token after the sender credentials change',async()=>{let grants=0;const send=sender(async url=>{if(url.endsWith('/token')){grants++;return token();}return receipt();});await send(mail,settings);await send(mail,{...settings,username:'another.sender'});expect(grants).toBe(2);});
it('renews once after an explicit unauthorized rejection and retries the rejected submission',async()=>{let grants=0,puts=0;const send=sender(async url=>{if(url.endsWith('/token')){grants++;return token();}puts++;return puts===1?json({errno:401,error:'expired'},401):receipt();});await send(mail,settings);expect(grants).toBe(2);expect(puts).toBe(2);});
it('bounds persistent authorization rejection and does not expose the response',async()=>{let puts=0;const send=sender(async url=>url.endsWith('/token')?token():(puts++,json({error:settings.password},401)));await expect(send(mail,settings)).rejects.toMatchObject({code:'notification_authentication'});expect(puts).toBe(2);});
it('does not delay a forbidden submission by unnecessarily renewing its token',async()=>{let grants=0,puts=0;const send=sender(async url=>{if(url.endsWith('/token')){grants++;return token();}puts++;return json({error:'forbidden'},403);});await expect(send(mail,settings)).rejects.toMatchObject({code:'notification_authentication'});expect(grants).toBe(1);expect(puts).toBe(1);});
it.each([
  ['business rejection',()=>json({errno:42,error:'provider secret sender-test-secret',entities:[]})],
  ['missing receipt',()=>json({errno:0,error:'success',entities:[]})],
  ['malformed JSON',()=>new Response('not-json',{status:200})],
  ['upstream failure',()=>json({error:'offline'},503)],
])('rejects a %s without treating the message as sent',async(_label,response)=>{const send=sender(async url=>url.endsWith('/token')?token():response());await expect(send(mail,settings)).rejects.toMatchObject({code:'notification_unavailable',message:'Report notification temporarily unavailable'});});
it('rejects a failed password grant without sending any message or echoing credentials',async()=>{let calls=0;const send=sender(async()=>{calls++;return json({error:'invalid_grant',error_description:settings.password},401);});await expect(send(mail,settings)).rejects.toMatchObject({code:'notification_authentication',message:'Report notification temporarily unavailable'});expect(calls).toBe(1);});
it('redacts network exceptions instead of leaking tokens or passwords',async()=>{const send=sender(async()=>{throw Error('private-test-token '+settings.password);});await expect(send(mail,settings)).rejects.toMatchObject({code:'notification_unavailable',message:'Report notification temporarily unavailable'});});
