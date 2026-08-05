import { Route, Routes } from 'react-router-dom';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import AiReviewHistoryPage from './pages/AiReviewHistoryPage';
import AiReviewResultPage from './pages/AiReviewResultPage';
import AiReviewRunPage from './pages/AiReviewRunPage';
import DuplicationCorpusPage from './pages/DuplicationCorpusPage';
import DuplicationDetectPage from './pages/DuplicationDetectPage';
import DuplicationHistoryPage from './pages/DuplicationHistoryPage';
import HomePage from './pages/HomePage';
import InnovationAssessmentPage from './pages/InnovationAssessmentPage';
import InnovationReportPage from './pages/InnovationReportPage';
import InnovationScoringPage from './pages/InnovationScoringPage';
import InnovationHistoryPage from './pages/InnovationHistoryPage';
import LedgerFilteredStatsPage from './pages/LedgerFilteredStatsPage';
import LedgerRecordsPage from './pages/LedgerRecordsPage';
import LocalPolishPage from './pages/LocalPolishPage';
import NormativeCheckPage from './pages/NormativeCheckPage';
import NormativeReportPage from './pages/NormativeReportPage';
import PolishHistoryPage from './pages/PolishHistoryPage';
import QualityDashboardPage from './pages/QualityDashboardPage';
import StudentQualityPortraitPage from './pages/StudentQualityPortraitPage';
import StudentReportResultsPage from './pages/StudentReportResultsPage';
import StudentReportSubmissionPage from './pages/StudentReportSubmissionPage';
import SupervisorReviewQueuePage from './pages/SupervisorReviewQueuePage';
import SupervisorReviewPage from './pages/SupervisorReviewPage';
import RuleConfigPage from './pages/RuleConfigPage';
import WholePolishPage from './pages/WholePolishPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/normative-check" element={<NormativeCheckPage />} />
      <Route path="/normative-reports" element={<NormativeReportPage />} />
      <Route path="/normative-reports/:reportId" element={<NormativeReportPage />} />
      <Route path="/ledger-records" element={<LedgerRecordsPage />} />
      <Route path="/ledger-stats" element={<LedgerFilteredStatsPage />} />
      <Route path="/quality-dashboard" element={<QualityDashboardPage />} />
      <Route path="/student-quality-portrait" element={<StudentQualityPortraitPage />} />
      <Route path="/student-quality-portrait/:studentId" element={<StudentQualityPortraitPage />} />
      <Route path="/student-report-submissions" element={<StudentReportSubmissionPage />} />
      <Route path="/student-report-results" element={<StudentReportResultsPage />} />
      <Route path="/student-report-results/:submissionId" element={<StudentReportResultsPage />} />
      <Route path="/supervisor-review-queue" element={<SupervisorReviewQueuePage />} />
      <Route path="/supervisor-review-queue/:submissionId" element={<SupervisorReviewPage />} />
      <Route path="/rule-config" element={<RuleConfigPage />} />
      <Route path="/duplication-corpus" element={<DuplicationCorpusPage />} />
      <Route path="/duplication-detect" element={<DuplicationDetectPage />} />
      <Route path="/duplication-history" element={<DuplicationHistoryPage />} />
      <Route path="/duplication-history/:reportId" element={<DuplicationHistoryPage />} />
      <Route path="/innovation-assessment" element={<InnovationAssessmentPage />} />
      <Route path="/innovation-history" element={<InnovationHistoryPage />} />
      <Route path="/innovation-assessments/:reportId" element={<InnovationReportPage />} />
      <Route path="/innovation-scoring" element={<InnovationScoringPage />} />
      <Route path="/ai-review" element={<AiReviewRunPage />} />
      <Route path="/ai-review/history" element={<AiReviewHistoryPage />} />
      <Route path="/ai-review/results/:reviewRunId" element={<AiReviewResultPage />} />
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
