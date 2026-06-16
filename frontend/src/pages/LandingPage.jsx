import { Link } from 'react-router-dom';

import { AppShell } from '../components/AppShell';
import { SectionCard } from '../components/SectionCard';

export function LandingPage() {
  return (
    <AppShell
      title="Medical Claim AI"
      subtitle="Choose the correct portal for your role. Employee and admin sign in separately."
      navItems={[]}
    >
      <SectionCard title="Select Portal" subtitle="Separate login pages">
        <div className="portal-grid">
          <Link className="portal-card" to="/employee/login">
            <p className="eyebrow">Employee</p>
            <h3>Employee Login</h3>
            <p>Upload medical bills, view claim history, and track claim status.</p>
          </Link>
          <Link className="portal-card" to="/admin/login">
            <p className="eyebrow">Admin</p>
            <h3>Admin Login</h3>
            <p>Review uploaded claims, validate data, approve, or reject submissions.</p>
          </Link>
        </div>
      </SectionCard>
    </AppShell>
  );
}
