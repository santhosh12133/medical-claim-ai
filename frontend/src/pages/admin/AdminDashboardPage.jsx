import { useEffect, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function AdminDashboardPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const pendingClaims = claims.filter((claim) => claim.status !== 'Approved' && claim.status !== 'Rejected').length;
  const rejectedClaims = claims.filter((claim) => claim.status === 'Rejected').length;
  const policyVerifiedClaims = claims.filter((claim) => claim.policy_decision).length;

  return (
    <SectionCard title="Claim Control Overview" subtitle="Admin dashboard">
      <div className="dashboard-grid">
        <article className="metric-card">
          <p className="eyebrow">Total Claims</p>
          <h3>{claims.length}</h3>
        </article>
        <article className="metric-card">
          <p className="eyebrow">Pending Queue</p>
          <h3>{pendingClaims}</h3>
        </article>
        <article className="metric-card">
          <p className="eyebrow">Rejected</p>
          <h3>{rejectedClaims}</h3>
        </article>
        <article className="metric-card">
          <p className="eyebrow">Policy Verified</p>
          <h3>{policyVerifiedClaims}</h3>
        </article>
      </div>
    </SectionCard>
  );
}
