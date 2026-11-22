import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function EmployeeDashboardPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const approvedStatuses = new Set(['Approved', 'Partially Approved']);
  const pendingClaims = claims.filter((claim) => !approvedStatuses.has(claim.status) && claim.status !== 'Rejected').length;
  const approvedClaims = claims.filter((claim) => approvedStatuses.has(claim.status)).length;
  const approvedAmount = claims
    .filter((claim) => approvedStatuses.has(claim.status))
    .reduce((total, claim) => total + Number(claim.final_approved_amount ?? claim.amount ?? 0), 0);

  return (
    <>
      <section className="card dashboard-welcome">
        <div>
          <p className="eyebrow">Claims at a glance</p>
          <h2>Welcome back</h2>
          <p className="hero-copy">Submit a medical bill and let OCR, policy retrieval and AI-assisted validation do the heavy lifting.</p>
        </div>
        <Link className="button-primary nav-button" to="/employee/upload">+ New claim</Link>
      </section>

      <SectionCard title="My Claim Overview" subtitle="Live account summary">
        <div className="dashboard-grid">
          <article className="metric-card"><p className="eyebrow">Total claims</p><h3>{claims.length}</h3><p className="metric-label">All submissions</p></article>
          <article className="metric-card"><p className="eyebrow">In review</p><h3>{pendingClaims}</h3><p className="metric-label">Awaiting a decision</p></article>
          <article className="metric-card"><p className="eyebrow">Approved</p><h3>{approvedClaims}</h3><p className="metric-label">Successful claims</p></article>
          <article className="metric-card"><p className="eyebrow">Approved value</p><h3>₹{approvedAmount.toLocaleString('en-IN')}</h3><p className="metric-label">Amount reimbursed</p></article>
        </div>
      </SectionCard>

      <SectionCard title="What happens next?" subtitle="Simple, transparent workflow">
        <div className="workflow-grid">
          <div><span className="workflow-step">01</span><strong>Upload</strong><p>Send your bill as a PDF or image.</p></div>
          <div><span className="workflow-step">02</span><strong>Extract</strong><p>OCR reads the hospital, treatment and amount.</p></div>
          <div><span className="workflow-step">03</span><strong>Verify</strong><p>Policy evidence is retrieved and evaluated.</p></div>
          <div><span className="workflow-step">04</span><strong>Track</strong><p>Follow the decision from your claims page.</p></div>
        </div>
      </SectionCard>
    </>
  );
}
