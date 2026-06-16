import { Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider, useAuth } from './auth/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AdminLayout } from './layouts/AdminLayout';
import { EmployeeLayout } from './layouts/EmployeeLayout';
import { AdminLoginPage } from './pages/AdminLoginPage';
import { EmployeeLoginPage } from './pages/EmployeeLoginPage';
import { LandingPage } from './pages/LandingPage';
import { AdminClaimsPage } from './pages/admin/AdminClaimsPage';
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage';
import { AdminReviewPage } from './pages/admin/AdminReviewPage';
import { EmployeeClaimsPage } from './pages/employee/EmployeeClaimsPage';
import { EmployeeDashboardPage } from './pages/employee/EmployeeDashboardPage';
import { EmployeeStatusPage } from './pages/employee/EmployeeStatusPage';
import { EmployeeUploadPage } from './pages/employee/EmployeeUploadPage';

function RootRedirect() {
  const { user, loading } = useAuth();

  if (loading) {
    return null;
  }

  if (!user) {
    return <LandingPage />;
  }

  return <Navigate to={user.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard'} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<LandingPage />} />
        <Route path="/employee/login" element={<EmployeeLoginPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />

        <Route element={<ProtectedRoute roles={["employee"]} />}>
          <Route path="/employee" element={<EmployeeLayout />}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<EmployeeDashboardPage />} />
            <Route path="upload" element={<EmployeeUploadPage />} />
            <Route path="claims" element={<EmployeeClaimsPage />} />
            <Route path="status" element={<EmployeeStatusPage />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute roles={["admin"]} />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<AdminDashboardPage />} />
            <Route path="claims" element={<AdminClaimsPage />} />
            <Route path="review" element={<AdminReviewPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
