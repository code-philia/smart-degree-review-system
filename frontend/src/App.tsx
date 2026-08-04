import { Route, Routes } from 'react-router-dom';
import { AuthSessionProvider } from './auth/AuthSessionProvider';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage';

function App() {
  return (
    <AuthSessionProvider>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route
          path="/auth"
          element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
        />
      </Routes>
    </AuthSessionProvider>
  );
}

export default App;
