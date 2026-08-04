import { Route, Routes } from 'react-router-dom';
import DemoAccountHelpPanel from './auth/DemoAccountHelpPanel';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route
        path="/auth"
        element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} helpSlot={<DemoAccountHelpPanel />} />}
      />
    </Routes>
  );
}

export default App;
 App;
