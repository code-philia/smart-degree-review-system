// Maintenance CLI: inherit the owner's existing local-account password, never reseed data.
const { withTransaction } = require('./database/db_runtime');
const { isSupervisionAccount } = require('./auth/supervisionPolicy');
const expected = { student01: 'STUDENT', supervisor01: 'SUPERVISOR', college_admin01: 'COLLEGE_ADMIN', school_admin01: 'SCHOOL_ADMIN' };

async function provisionSupervisionAdmin() {
  const fs = require('fs');
  const file = require('./database').getDbPath();
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) throw new Error('指定的现有数据库不存在，未创建管理员');
  return withTransaction(async tx => {
    const local = await tx.all("SELECT id,username,role,password_hash FROM auth_users WHERE id IN ('student01','supervisor01','college_admin01','school_admin01')");
    if (local.length !== 4 || local.some(u => u.id !== u.username || u.role !== expected[u.id])
        || new Set(local.map(u => u.password_hash)).size !== 1 || !/^\$2[aby]\$/.test(local[0].password_hash)) {
      throw new Error('现有本地账号身份或共享密码不一致，未创建管理员');
    }
    const existing = await tx.all("SELECT id,username,role,scope,password_hash FROM auth_users WHERE id='admin' OR username='admin'");
    if (existing.length) {
      if (existing.length !== 1 || !isSupervisionAccount(existing[0]) || existing[0].password_hash !== local[0].password_hash) {
        throw new Error('存在不匹配的 admin 账号，未覆盖现有账号');
      }
      return { created: false, username: 'admin' };
    }
    await tx.run("INSERT INTO auth_users(id,username,display_name,password_hash,role,scope,default_locale) VALUES ('admin','admin','管理员',?,'SCHOOL_ADMIN','SCHOOL','zh')", [local[0].password_hash]);
    return { created: true, username: 'admin' };
  });
}
module.exports = { provisionSupervisionAdmin };
if (require.main === module) {
  provisionSupervisionAdmin().then(result => { console.log(JSON.stringify(result)); return require('./database').closeDb(); })
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
