import { useLayoutEffect } from 'react';
import { getLocale, setLocale } from './i18n/locale';
import { readLinkLocale, requestedReturnTo } from './nav/reportLinks';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { canonicalReviewUrl, REVIEW_ROUTES } from './nav/reviewRoutes';
import AppShell from './layout/AppShell';
import RequireSession from './auth/RequireSession';
import AuthPage from './pages/AuthPage';
import NotFoundPage from './pages/NotFoundPage';
import NormativeCheckPage from './pages/NormativeCheckPage';
import NormativeReportPage from './pages/NormativeReportPage';
import PaperLintReportPage from './pages/PaperLintReportPage';
import { useAuthSession } from './auth/AuthSessionProvider';
import { LoadingState } from './components/ui';
import SupervisionShell, { RequireSupervision, SupervisionChinese } from './supervision/SupervisionShell';
import SupervisionLoginPage from './supervision/SupervisionLoginPage';
import { SupervisionReportsPage, SupervisionFeedbackPage, SupervisionReportPage } from './supervision/SupervisionPages';

function LegacyReviewRedirect() {
  const location = useLocation();
  const target = canonicalReviewUrl(location.pathname + location.search + location.hash);
  return <Navigate replace to={target || REVIEW_ROUTES.upload} state={location.state} />;
}
function SignInRoute(){
  const location=useLocation();
  const { status, user }=useAuthSession();
  const returnTo=requestedReturnTo(location.state, location.search);
  if(status==='loading'){
    return <main className="session-loading"><LoadingState label="正在加载登录状态…"/></main>;
  }
  if(user) return <Navigate replace to={user.accessMode === 'supervision' ? '/admin/reports' : returnTo || REVIEW_ROUTES.upload}/>;
  return <AuthPage returnTo={returnTo}/>;
}
function UserWorkspace() {
  const { user } = useAuthSession();
  return user?.accessMode === 'supervision' ? <Navigate replace to="/admin/reports" /> : <AppShell />;
}

function App() {
  const location = useLocation();
  useLayoutEffect(() => {
    const pathname = location.pathname.toLowerCase();
    if (pathname === '/admin' || pathname.startsWith('/admin/')) return;
    const requested = readLinkLocale(location.search);
    if (requested && requested !== getLocale()) setLocale(requested);
  }, [location.pathname, location.search]);
  return (
    <Routes>
      <Route path="/admin/login" element={<SupervisionChinese><SupervisionLoginPage /></SupervisionChinese>} />
      <Route element={<SupervisionChinese><RequireSupervision /></SupervisionChinese>}>
        <Route path="/admin" element={<SupervisionShell />}>
          <Route index element={<Navigate replace to="/admin/reports" />} />
          <Route path="reports" element={<SupervisionReportsPage />} />
          <Route path="feedback" element={<SupervisionFeedbackPage />} />
          <Route path="reports/:reportId" element={<SupervisionReportPage />} />
          <Route path="*" element={<Navigate replace to="/admin/reports" />} />
        </Route>
      </Route>
      <Route
        path="/auth"
        element={<SignInRoute />}
      />

      <Route element={<RequireSession />}>
        <Route element={<UserWorkspace />}>
          <Route path="/" element={<Navigate replace to={REVIEW_ROUTES.upload} />} />
          <Route path={REVIEW_ROUTES.upload} element={<NormativeCheckPage key="ordinary" mode="thirty" />} />
          <Route path={REVIEW_ROUTES.semantic} element={<LegacyReviewRedirect />} />
          <Route path={REVIEW_ROUTES.history} element={<NormativeReportPage mode="thirty" />} />
          <Route path={`${REVIEW_ROUTES.history}/pdf/:reportId`} element={<PaperLintReportPage mode="thirty" />} />
          <Route path="/thirty-rules-check" element={<LegacyReviewRedirect />} />
          <Route path="/semantic-rules-check" element={<LegacyReviewRedirect />} />
          <Route path="/thirty-rules-check/reports" element={<LegacyReviewRedirect />} />
          <Route path="/thirty-rules-check/reports/pdf/:reportId" element={<LegacyReviewRedirect />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default App;
