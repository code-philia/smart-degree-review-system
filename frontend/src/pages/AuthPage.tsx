import { LanguageSwitch } from '../i18n/LanguageSwitch';
import { RichMessage } from '../i18n/jsx-runtime';
import { ArrowUpRight } from 'lucide-react';
import AuthCampusScene from './authCampus/AuthCampusScene';
import TrialAccountEntry from '../auth/TrialAccountEntry';
import { canonicalReviewUrl } from '../nav/reviewRoutes';
import './auth-campus.css';

function JaccountEntry({returnTo}:{returnTo?:string|null}) {
  const error = new URLSearchParams(window.location.search).get('jaccount_error');
  const errors: Record<string, string> = {
    state: 'jAccount 登录已过期，请重新登录。',
    provider: 'jAccount 登录暂未完成，请重试。',
    denied: '已取消 jAccount 登录，可重新登录。',
    unavailable: 'jAccount 登录暂不可用，请稍后重试或联系系统管理员。',
    forbidden_role: '此账号无法通过 jAccount 登录，请联系系统管理员。',
  };
  return (
    <section aria-label="校内账号登录">
      <a href={returnTo?`/api/auth/jaccount?return_to=${encodeURIComponent(returnTo)}`:'/api/auth/jaccount'} className="login-button">
        使用 jAccount 登录
        <ArrowUpRight size={18} strokeWidth={1.5} aria-hidden="true" />
      </a>
      <p className="hint"><RichMessage name="login-hint">交大师生可使用校内账号统一认证</RichMessage></p>
      {error && typeof errors[error] === 'string' ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {errors[error]}
        </p>
      ) : null}
    </section>
  );
}

export default function AuthPage({returnTo}:{returnTo?:string|null}={}) {
  return (
    <main className="campus-signin">
      <AuthCampusScene />
      <LanguageSwitch login />
      <div className="page">
 <header className="masthead masthead-layout-anchor" aria-hidden="true" inert={true}>
  <div className="brand"><img src="/login-schoolmark.jpg" alt="上海交通大学校徽" /><h1><RichMessage name="login-brand">智慧学位AI评阅辅助系统</RichMessage></h1></div>
  <span className="trial">试点验证版 V0.9</span>
  <p className="description">本系统依托人工智能技术，对照国家标准与学校规范，为学位论文提供格式排版、文字表述、语言规范等自动化检测，并给出修改建议。<br /><RichMessage name="login-description-rest">论文数据均在校内处理，保障信息安全。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议，我们将持续优化。</RichMessage></p>
 </header>
 <div className="composition">
  <div className="scene-space" aria-hidden="true"></div>
  <section className="signin" aria-label="身份认证区域">
   <p className="welcome">欢迎使用</p><h2><RichMessage name="login-card-brand">智慧学位AI评阅辅助系统</RichMessage></h2>
   <JaccountEntry returnTo={canonicalReviewUrl(returnTo)} />
   <section className="services" aria-label="学位论文规范性检测">
    <div className="service"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 7c-3-3-7-3-9-2v14c4-2 7-1 9 1 2-2 5-3 9-1V5c-2-1-6-1-9 2v13M16 11l2 2 4-4"/></svg><span>格式排版</span></div>
    <div className="service"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4H5a1 1 0 0 0-1 1v3m12-4h3a1 1 0 0 1 1 1v3M4 16v3a1 1 0 0 0 1 1h3m8 0h3a1 1 0 0 0 1-1v-3M7 12h10"/></svg><span>文字表述</span></div>
    <div className="service"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 15v5zm0 0h16"/></svg><span>语言规范</span></div>
   </section>
  </section>
 </div>
 <footer role="contentinfo" className="preview-tools filing-footer" aria-label="网站备案信息"><p className="filing-number">沪交ICP备20260352</p></footer>
</div>
      <div className="v9-header-layer">
<header className="reference-masthead">
  <div className="reference-brand"><img src="/login-schoolmark.jpg" alt="上海交通大学校徽" /><h1><RichMessage name="login-brand">智慧学位AI评阅辅助系统</RichMessage></h1></div>
  <div className="reference-trial"><TrialAccountEntry /></div>
  <p className="reference-description" aria-label="系统说明">本系统依托人工智能技术，对照国家标准与学校规范，为学位论文提供格式排版、文字表述、语言规范等自动化检测，并给出修改建议。<br /><RichMessage name="login-description-rest">论文数据均在校内处理，保障信息安全。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议，我们将持续优化。</RichMessage></p>
 </header></div>
    </main>
  );
}
