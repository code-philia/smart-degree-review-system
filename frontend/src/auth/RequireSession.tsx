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
    return <Navigate replace to="/auth" state={{ from: location.pathname + location.search + location.hash }} />;
  }
  return <Outlet />;
}
