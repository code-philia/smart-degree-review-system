import { Route, Routes } from 'react-router-dom';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage';
import NormativeCheckPage from './pages/NormativeCheckPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/normative-check" element={<NormativeCheckPage />} />
      <Route
        path="/auth"
        element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
      />
    </Routes>
  );
}

export default App;
