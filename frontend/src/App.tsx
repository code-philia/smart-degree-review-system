import { Route, Routes } from 'react-router-dom';
import LocalAccountLoginForm from './auth/LocalAccountLoginForm';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/auth" element={<AuthPage accountFormSlot={<LocalAccountLoginForm />} />} />
    </Routes>
  );
}

export default App;
