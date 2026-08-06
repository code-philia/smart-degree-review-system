const demoAccounts = [
  {
    username: 'student01',
    role: '学生',
    scope: '校内学习场景',
  },
  {
    username: 'supervisor01',
    role: '导师',
    scope: '学院指导场景',
  },
  {
    username: 'college_admin01',
    role: '学院管理人员',
    scope: '学院级管理场景',
  },
  {
    username: 'school_admin01',
    role: '学校管理人员',
    scope: '学校级管理场景',
  },
] as const;

function DemoAccountHelpPanel() {
  return (
    <details
      className="rounded border border-slate-200 bg-slate-50 p-5 shadow-sm"
      id="demo-help"
      open
      aria-label="演示账号与登录帮助"
    >
      <summary className="cursor-pointer list-none text-lg font-black text-slate-900 outline-none marker:hidden">
        试用账号说明
      </summary>

      <p className="mt-3 text-sm leading-6 text-slate-600">
        试点版本目前仅支持账号密码方式登录。默认演示密码为
        ArcDemo123!，四个账号分别对应不同角色，可用于体验登录后的界面与操作。
      </p>

      <div className="mt-4 grid gap-3" id="roles" aria-label="四类演示账号">
        {demoAccounts.map((account) => (
          <article key={account.username} className="rounded bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-bold text-slate-900">{account.username}</h3>
              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                {account.role}
              </span>
            </div>
            <dl className="mt-2 grid gap-1 text-sm text-slate-600 sm:grid-cols-2">
              <div>
                <dt className="font-semibold text-slate-500">初始密码</dt>
                <dd className="font-medium text-slate-800">ArcDemo123!</dd>
              </div>
              <div>
                <dt className="font-semibold text-slate-500">适用范围</dt>
                <dd>{account.scope}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>

      <div className="mt-4 rounded border border-amber-100 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
        说明：试点版本尚未接入 jAccount、短信验证码或扫码登录；如需登录，请直接使用上方试用账号与密码。
      </div>
    </details>
  );
}

export default DemoAccountHelpPanel;
