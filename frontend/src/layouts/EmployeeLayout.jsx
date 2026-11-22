import { Outlet } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';

export function EmployeeLayout() {
  const { signOut } = useAuth();

  return (
    <AppShell
      title="Employee Workspace"
      roleLabel="Employee"
      subtitle="Upload bills, track claim decisions, and ask what your policy covers."
      navItems={[
        { label: 'Overview', to: '/employee/dashboard' },
        { label: 'Upload Invoice', to: '/employee/upload' },
        { label: 'My Claims', to: '/employee/claims' },
        { label: 'Claim Status', to: '/employee/status' },
        { label: 'Coverage Assistant', to: '/employee/assistant' },
      ]}
      actions={<button type="button" className="secondary nav-button" onClick={signOut}>Logout</button>}
    >
      <Outlet />
    </AppShell>
  );
}
