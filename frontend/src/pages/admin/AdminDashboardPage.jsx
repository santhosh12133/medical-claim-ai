import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

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
  const approvedClaims = claims.filter((claim) => claim.status === 'Approved').length;

  return (
    <>
      <section className="card dashboard-welcome">
        <div>
          <p className="eyebrow">Operations overview</p>
          <h2>Claim control center</h2>
          <p className="hero-copy">Monitor submissions, policy verification and the cases that need human attention.</p>
        </div>
        <Link className="button-primary nav-button" to="/admin/review">Open review queue</Link>
      </section>

      <SectionCard title="Claim Control Overview" subtitle="Live processing metrics">
        <div className="dashboard-grid">
          <article className="metric-card"><p className="eyebrow">Total claims</p><h3>{claims.length}</h3><p className="metric-label">All submissions</p></article>
          <article className="metric-card"><p className="eyebrow">Pending queue</p><h3>{pendingClaims}</h3><p className="metric-label">Need attention</p></article>
          <article className="metric-card"><p className="eyebrow">Approved</p><h3>{approvedClaims}</h3><p className="metric-label">Completed claims</p></article>
          <article className="metric-card"><p className="eyebrow">Policy verified</p><h3>{policyVerifiedClaims}</h3><p className="metric-label">RAG checks completed</p></article>
        </div>
      </SectionCard>

      <SectionCard title="Processing health" subtitle="Current queue signals">
        <div className="health-grid">
          <div className="health-item"><span className="health-dot health-dot--green" /><div><strong>Policy verification</strong><p>{policyVerifiedClaims} claims have policy evidence.</p></div></div>
          <div className="health-item"><span className="health-dot health-dot--amber" /><div><strong>Human review</strong><p>{pendingClaims} claims are still in the queue.</p></div></div>
          <div className="health-item"><span className="health-dot health-dot--red" /><div><strong>Rejected</strong><p>{rejectedClaims} claims were rejected.</p></div></div>
        </div>
      </SectionCard>
    </>
  );
}
