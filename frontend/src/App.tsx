import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { canonicalReviewUrl, REVIEW_ROUTES } from './nav/reviewRoutes';
import AppShell from './layout/AppShell';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
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

function App() {
  return (
    <Routes>
      <Route
        path="/auth"
        element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
      />

      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate replace to={REVIEW_ROUTES.upload} />} />
          <Route path={REVIEW_ROUTES.upload} element={<NormativeCheckPage key="ordinary" mode="thirty" />} />
          <Route path={REVIEW_ROUTES.semantic} element={<NormativeCheckPage key="semantic" mode="semantic" />} />
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
