import type { ReactNode } from 'react';

type AuthPageProps = {
  accountFormSlot?: ReactNode;
  helpSlot?: ReactNode;
};

function HeroPanel() {
  return (
    <section className="relative flex min-h-[520px] overflow-hidden bg-gradient-to-br from-[#071B5F] via-[#1C62D8] to-[#58D9F6] px-10 py-12 text-white">
      <div className="absolute inset-0 opacity-40" aria-hidden="true">
        <div className="absolute left-10 top-12 h-40 w-40 rounded-full bg-cyan-300 blur-3xl" />
        <div className="absolute bottom-8 right-8 h-56 w-56 rounded-full bg-blue-200 blur-3xl" />
        <div className="absolute bottom-0 left-1/4 h-1/2 w-1/2 rotate-12 border-t border-cyan-100/60" />
        <div className="absolute bottom-0 left-1/3 h-2/3 w-2/3 -rotate-6 border-t border-blue-100/40" />
      </div>
      <div className="relative z-10 flex w-full flex-col items-center justify-start text-center">
        <img src="/brand-mark.jpg" alt="" className="h-16 w-16 rounded-full object-cover ring-4 ring-white/30" />
        <p className="mt-6 text-sm font-semibold tracking-[0.3em] text-cyan-100">智慧学位 AI 评阅辅助系统 · 试点验证版 V0.9</p>
        <h1 className="mt-4 text-4xl font-black leading-tight tracking-wide md:text-5xl">统一身份认证</h1>
        <p className="mt-5 max-w-md text-lg leading-8 text-blue-50">
          面向学生、导师、学院管理人员和学校管理人员的账号登录入口。
        </p>
      </div>
    </section>
  );
}

function UnsupportedQrColumn() {
  return (
    <section className="flex w-56 flex-col items-center text-center" aria-label="扫码登录说明">
      <h2 className="text-xl font-bold text-slate-800">其他登录方式</h2>
      <div className="mt-6 flex h-44 w-44 items-center justify-center border border-dashed border-slate-300 bg-slate-50 text-sm font-semibold leading-6 text-slate-500">
        微信扫码、交我办与短信验证码登录
        <br />
        试点版本暂未开放
      </div>
      <p className="mt-5 text-sm leading-6 text-slate-500">请使用右侧账号密码方式登录。</p>
    </section>
  );
}

function DefaultAccountSlot() {
  return (
    <div className="space-y-4" aria-label="账号登录表单">
      <div className="flex h-14 items-center border border-[#D6D6D6] px-4 text-slate-400">
        <span className="mr-3 text-lg" aria-hidden="true">👤</span>
        <span>请输入账号</span>
      </div>
      <div className="flex h-14 items-center border border-[#D6D6D6] px-4 text-slate-400">
        <span className="mr-3 text-lg" aria-hidden="true">🔒</span>
        <span>请输入密码</span>
      </div>
    </div>
  );
}

function AuthPage({ accountFormSlot, helpSlot }: AuthPageProps) {
  return (
    <main className="min-h-screen bg-white text-[#333333]">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 py-10 lg:flex-row lg:items-start lg:gap-14">
        <div className="w-full lg:w-[43%]">
          <HeroPanel />
        </div>

        <section className="flex flex-1 flex-col gap-10 pt-2 lg:flex-row lg:items-start" aria-label="身份认证区域">
          <UnsupportedQrColumn />

          <section className="w-full max-w-[370px]" aria-label="账号密码登录区域">
            <h2 className="text-2xl font-black text-slate-900">登录本地账号</h2>
            <div className="mt-6">{accountFormSlot ?? <DefaultAccountSlot />}</div>
            <div className="mt-5 flex justify-between text-base font-semibold text-[#4A75E8]">
              <a className="hover:underline focus:underline" href="#password">忘记密码/用户名</a>
              <a className="hover:underline focus:underline" href="#roles">试用账号说明</a>
            </div>
            <p id="password" className="mt-4 rounded border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-600">
              如忘记账号或密码，请联系系统管理员重置。试点阶段可直接使用下方试用账号登录体验。
            </p>
            <div className="mt-4 text-center text-sm text-slate-500 underline underline-offset-4">
              短信验证码登录不属于本版本实现范围
            </div>
            {helpSlot ? <div className="mt-6">{helpSlot}</div> : null}
          </section>
        </section>
      </section>
    </main>
  );
}

export default AuthPage;
