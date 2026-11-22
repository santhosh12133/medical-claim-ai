import { AppShell } from '../components/AppShell';

const NAV = [
  { label: 'Overview', to: '/employee/dashboard', icon: 'overview' },
  { label: 'Submit a bill', to: '/employee/upload', icon: 'submit' },
  { label: 'My claims', to: '/employee/claims', icon: 'claims' },
  { label: 'Coverage questions', to: '/employee/assistant', icon: 'assistant' },
];

export function EmployeeLayout() {
  return <AppShell navItems={NAV} />;
}
