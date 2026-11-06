import {expect,it} from 'vitest';import{createRequire}from'node:module';
const require=createRequire(import.meta.url);
const {notificationEmail}=require('../src/notifications/emailPolicy');
it('resolves an existing authenticated campus identity without another OAuth login',()=>{
  expect(notificationEmail({id:'jaccount:existing',username:'jaccount:campus.person',role:'STUDENT',email:null})).toBe('campus.person@sjtu.edu.cn');
});
it.each(['student01','supervisor01','college_admin01','school_admin01'])('keeps %s on the fixed mailbox after a role reassignment',username=>{
  expect(notificationEmail({id:username,username,role:'SUPERVISOR',email:'wrong@example.test'})).toBe('123090058@link.cuhk.edu.cn');
});
it('uses the fixed mailbox for an additional administrator identity',()=>{
  expect(notificationEmail({id:'staff-123',username:'staff',role:'COLLEGE_ADMIN',email:'other@sjtu.edu.cn'})).toBe('123090058@link.cuhk.edu.cn');
});
it('does not confuse a campus identity with a similarly named local trial account',()=>{
  expect(notificationEmail({id:'jaccount:123',username:'jaccount:student01',role:'STUDENT',email:null})).toBe('student01@sjtu.edu.cn');
});
