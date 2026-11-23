import { Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider } from './auth/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AdminLayout } from './layouts/AdminLayout';
import { EmployeeLayout } from './layouts/EmployeeLayout';
import { AssistantPage } from './pages/AssistantPage';
import { SignInPage } from './pages/SignInPage';
import { AdminClaimsPage } from './pages/admin/AdminClaimsPage';
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage';
import { AdminPoliciesPage } from './pages/admin/AdminPoliciesPage';
import { AdminReviewPage } from './pages/admin/AdminReviewPage';
import { EmployeeClaimsPage } from './pages/employee/EmployeeClaimsPage';
import { EmployeeDashboardPage } from './pages/employee/EmployeeDashboardPage';
import { EmployeeUploadPage } from './pages/employee/EmployeeUploadPage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Separate sign-in portals; each accepts only its own kind of account. */}
        <Route path="/" element={<Navigate to="/employee/login" replace />} />
        <Route path="/login" element={<Navigate to="/employee/login" replace />} />
        <Route path="/employee/login" element={<SignInPage portal="employee" />} />
        <Route path="/admin/login" element={<SignInPage portal="admin" />} />

        <Route element={<ProtectedRoute roles={['employee']} />}>
          <Route path="/employee" element={<EmployeeLayout />}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<EmployeeDashboardPage />} />
            <Route path="upload" element={<EmployeeUploadPage />} />
            <Route path="claims" element={<EmployeeClaimsPage />} />
            <Route path="status" element={<Navigate to="/employee/claims" replace />} />
            <Route path="assistant" element={<AssistantPage audience="employee" />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute roles={['admin']} />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<AdminDashboardPage />} />
            <Route path="review" element={<AdminReviewPage />} />
            <Route path="claims" element={<AdminClaimsPage />} />
            <Route path="policies" element={<AdminPoliciesPage />} />
            <Route path="assistant" element={<AssistantPage audience="admin" />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/employee/login" replace />} />
      </Routes>
    </AuthProvider>
  );
}
