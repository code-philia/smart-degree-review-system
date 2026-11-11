import { getLocale } from '../i18n/locale';
import { signInDestination } from '../nav/reportLinks';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { LoadingState } from '../components/ui';
import { useAuthSession } from './AuthSessionProvider';

export default function RequireSession() {
  const { status, user } = useAuthSession();
  const location = useLocation();
  if (status === 'loading') {
    return (
      <main className="session-loading">
        <LoadingState label="正在加载登录状态…" />
      </main>
    );
  }
  if (!user) {
    return <Navigate replace to={signInDestination(location.pathname + location.search + location.hash, getLocale())} state={{ from: location.pathname + location.search + location.hash }} />;
  }
  return <Outlet />;
}
