function DemoAccountHelpPanel() {
  return (
    <details
      className="demo-help rounded-xl border border-slate-200 bg-slate-50 p-4"
      id="demo-help"
      aria-label="本地账号登录帮助"
    >
      <summary className="cursor-pointer text-sm font-semibold text-slate-700">本地账号登录帮助</summary>

      <p className="mt-3 text-sm leading-6 text-slate-600">
        本地账号由系统管理员统一创建和管理。如需试用账号，请向管理员申请，不在登录页面公开账号或密码。
      </p>

      <div className="mt-4 rounded border border-amber-100 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
        交大师生可使用上方 jAccount 入口登录；本地账号登录继续保留。
      </div>
    </details>
  );
}

export default DemoAccountHelpPanel;
