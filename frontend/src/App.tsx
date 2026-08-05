import { Route, Routes } from 'react-router-dom';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import DuplicationCorpusPage from './pages/DuplicationCorpusPage';
import DuplicationDetectPage from './pages/DuplicationDetectPage';
import DuplicationHistoryPage from './pages/DuplicationHistoryPage';
import HomePage from './pages/HomePage';
import InnovationAssessmentPage from './pages/InnovationAssessmentPage';
import InnovationScoringPage from './pages/InnovationScoringPage';
import LocalPolishPage from './pages/LocalPolishPage';
import NormativeCheckPage from './pages/NormativeCheckPage';
import NormativeReportPage from './pages/NormativeReportPage';
import PolishHistoryPage from './pages/PolishHistoryPage';
import RuleConfigPage from './pages/RuleConfigPage';
import WholePolishPage from './pages/WholePolishPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/normative-check" element={<NormativeCheckPage />} />
      <Route path="/normative-reports" element={<NormativeReportPage />} />
      <Route path="/normative-reports/:reportId" element={<NormativeReportPage />} />
      <Route path="/rule-config" element={<RuleConfigPage />} />
      <Route path="/duplication-corpus" element={<DuplicationCorpusPage />} />
      <Route path="/duplication-detect" element={<DuplicationDetectPage />} />
      <Route path="/duplication-history" element={<DuplicationHistoryPage />} />
      <Route path="/duplication-history/:reportId" element={<DuplicationHistoryPage />} />
      <Route path="/innovation-assessment" element={<InnovationAssessmentPage />} />
      <Route path="/innovation-scoring" element={<InnovationScoringPage />} />
      <Route path="/whole-polish" element={<WholePolishPage />} />
      <Route path="/whole-polish/:resultId" element={<WholePolishPage />} />
      <Route path="/local-polish" element={<LocalPolishPage />} />
      <Route path="/polish-history" element={<PolishHistoryPage />} />
      <Route path="/polish-history/:polishType/:resultId" element={<PolishHistoryPage />} />
      <Route
        path="/auth"
        element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
      />
    </Routes>
  );
}

export default App;
