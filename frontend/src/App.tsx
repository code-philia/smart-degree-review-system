import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { canonicalReviewUrl, REVIEW_ROUTES } from './nav/reviewRoutes';
import AppShell from './layout/AppShell';
import RequireSession from './auth/RequireSession';
import AuthPage from './pages/AuthPage';
import NotFoundPage from './pages/NotFoundPage';
import NormativeCheckPage from './pages/NormativeCheckPage';
import NormativeReportPage from './pages/NormativeReportPage';
import PaperLintReportPage from './pages/PaperLintReportPage';

function LegacyReviewRedirect() {
  const location = useLocation();
  const target = canonicalReviewUrl(location.pathname + location.search + location.hash);
  return <Navigate replace to={target || REVIEW_ROUTES.upload} state={location.state} />;
}
function SignInRoute(){
  const location=useLocation();
  return <AuthPage returnTo={canonicalReviewUrl(location.state?.from)}/>;
}

function App() {
  return (
    <Routes>
      <Route
        path="/auth"
        element={<SignInRoute />}
      />

      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
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
