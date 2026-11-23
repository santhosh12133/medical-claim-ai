import { Navigate, Outlet } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { homeFor, loginFor } from '../pages/SignInPage';

export function ProtectedRoute({ roles }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="page-loading" role="status"><span className="spinner" aria-hidden="true" />Loading your workspace…</div>;
  }
  if (!user) return <Navigate to={loginFor(roles?.[0])} replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user)} replace />;
  return <Outlet />;
}
