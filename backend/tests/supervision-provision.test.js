import { createRequire } from 'node:module';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';
const require=createRequire(import.meta.url);
const db=require('../src/database');
const {provisionSupervisionAdmin}=require('../src/provisionSupervisionAdmin');
const harness=db.createTestDatabaseHarness({label:'supervision-provision',seedDefault:true});
beforeEach(()=>harness.setup());afterEach(()=>harness.cleanup());
describe('supervision administrator provisioning',()=>{
 it('adds only the exact read-only identity and inherits the existing shared password',async()=>{
  const before=await db.all('SELECT * FROM auth_users ORDER BY id');
  expect(await provisionSupervisionAdmin()).toEqual({created:true,username:'admin'});
  const admin=await db.get("SELECT * FROM auth_users WHERE id='admin'");
  expect(admin).toMatchObject({username:'admin',role:'SCHOOL_ADMIN',scope:'SCHOOL',default_locale:'zh',password_hash:before[0].password_hash});
  expect(await db.all("SELECT * FROM auth_users WHERE id!='admin' ORDER BY id")).toEqual(before);
  expect(await provisionSupervisionAdmin()).toEqual({created:false,username:'admin'});
  expect((await db.get('SELECT count(*) AS n FROM auth_users')).n).toBe(5);
 });
 it('does not overwrite an unrelated account using the requested name',async()=>{
  await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES ('existing-person','admin','existing-hash','STUDENT','COLLEGE')");
  const before=await db.all('SELECT * FROM auth_users ORDER BY id');
  await expect(provisionSupervisionAdmin()).rejects.toThrow('未覆盖现有账号');
  expect(await db.all('SELECT * FROM auth_users ORDER BY id')).toEqual(before);
 });
 it('does not reset a mismatched source password',async()=>{
  await db.run("UPDATE auth_users SET password_hash='different' WHERE id='student01'");
  const before=await db.all('SELECT * FROM auth_users ORDER BY id');
  await expect(provisionSupervisionAdmin()).rejects.toThrow('共享密码不一致');
  expect(await db.all('SELECT * FROM auth_users ORDER BY id')).toEqual(before);
 });
});
