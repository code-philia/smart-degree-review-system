import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppearanceProvider } from './AppearanceProvider';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthSessionProvider } from './auth/AuthSessionProvider';
import './index.css';
import './i18n/english.css';
import './appearance.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppearanceProvider>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </AppearanceProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
