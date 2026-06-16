import { Outlet } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';

export function AdminLayout() {
  const { signOut } = useAuth();

  return (
    <AppShell
      title="Admin Control Center"
      roleLabel="Admin"
      subtitle="Review incoming claims, inspect OCR validation, and approve or reject submissions."
      navItems={[
        { label: 'Overview', to: '/admin/dashboard' },
        { label: 'All Claims', to: '/admin/claims' },
        { label: 'Review Queue', to: '/admin/review' },
      ]}
      actions={<button type="button" className="secondary nav-button" onClick={signOut}>Logout</button>}
    >
      <Outlet />
    </AppShell>
  );
}
