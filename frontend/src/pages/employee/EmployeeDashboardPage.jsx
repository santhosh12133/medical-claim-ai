import { useEffect, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function EmployeeDashboardPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const pendingClaims = claims.filter((claim) => claim.status !== 'Approved' && claim.status !== 'Rejected').length;
  const approvedClaims = claims.filter((claim) => claim.status === 'Approved').length;

  return (
    <SectionCard title="My Claim Overview" subtitle="Employee dashboard">
      <div className="dashboard-grid">
        <article className="metric-card">
          <p className="eyebrow">My Claims</p>
          <h3>{claims.length}</h3>
        </article>
        <article className="metric-card">
          <p className="eyebrow">Waiting Review</p>
          <h3>{pendingClaims}</h3>
        </article>
        <article className="metric-card">
          <p className="eyebrow">Approved</p>
          <h3>{approvedClaims}</h3>
        </article>
      </div>
    </SectionCard>
  );
}
