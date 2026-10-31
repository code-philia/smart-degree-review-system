import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './layout/AppShell';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import RequireSession from './auth/RequireSession';
import AuthPage from './pages/AuthPage';
import NotFoundPage from './pages/NotFoundPage';
import NormativeCheckPage from './pages/NormativeCheckPage';
import NormativeReportPage from './pages/NormativeReportPage';
import PaperLintReportPage from './pages/PaperLintReportPage';

function App() {
  return (
    <Routes>
      <Route
        path="/auth"
        element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
      />

      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate replace to="/thirty-rules-check" />} />
          <Route path="/thirty-rules-check" element={<NormativeCheckPage key="ordinary" mode="thirty" />} />
          <Route path="/semantic-rules-check" element={<NormativeCheckPage key="semantic" mode="semantic" />} />
          <Route path="/thirty-rules-check/reports" element={<NormativeReportPage mode="thirty" />} />
          <Route path="/thirty-rules-check/reports/pdf/:reportId" element={<PaperLintReportPage mode="thirty" />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default App;
