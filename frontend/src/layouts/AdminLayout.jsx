import { Outlet } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';

export function AdminLayout() {
  const { signOut } = useAuth();

  return (
    <AppShell
      title="Admin Control Center"
      roleLabel="Admin"
      subtitle="Review claims with cited policy evidence, manage the policy knowledge base, and monitor automated decisions."
      navItems={[
        { label: 'Overview', to: '/admin/dashboard' },
        { label: 'All Claims', to: '/admin/claims' },
        { label: 'Review Queue', to: '/admin/review' },
        { label: 'Policies', to: '/admin/policies' },
        { label: 'Policy Assistant', to: '/admin/assistant' },
      ]}
      actions={<button type="button" className="secondary nav-button" onClick={signOut}>Logout</button>}
    >
      <Outlet />
    </AppShell>
  );
}
