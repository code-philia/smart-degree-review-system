import { Route, Routes } from 'react-router-dom';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import DuplicationCorpusPage from './pages/DuplicationCorpusPage';
import HomePage from './pages/HomePage';
import NormativeCheckPage from './pages/NormativeCheckPage';
import NormativeReportPage from './pages/NormativeReportPage';
import RuleConfigPage from './pages/RuleConfigPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/normative-check" element={<NormativeCheckPage />} />
      <Route path="/normative-reports" element={<NormativeReportPage />} />
      <Route path="/normative-reports/:reportId" element={<NormativeReportPage />} />
      <Route path="/rule-config" element={<RuleConfigPage />} />
      <Route path="/duplication-corpus" element={<DuplicationCorpusPage />} />
      <Route
        path="/auth"
        element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
      />
    </Routes>
  );
}

export default App;
