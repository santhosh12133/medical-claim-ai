import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function AdminDashboardPage() {
  const [claims, setClaims] = useState([]);
  const [decisionMetrics, setDecisionMetrics] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get('/claims'),
      api.get('/rag/metrics/decisions'),
    ])
      .then(([claimsResponse, metricsResponse]) => {
        setClaims(claimsResponse.data);
        setDecisionMetrics(metricsResponse.data);
      })
      .catch(() => {
        api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
      });
  }, []);

  const pendingClaims = claims.filter((claim) => claim.status !== 'Approved' && claim.status !== 'Rejected').length;
  const rejectedClaims = claims.filter((claim) => claim.status === 'Rejected').length;
  const processingClaims = claims.filter((claim) => claim.status === 'Processing').length;
  const policyVerifiedClaims = claims.filter((claim) => claim.policy_decision).length;
  const approvedClaims = claims.filter((claim) => claim.status === 'Approved').length;

  return (
    <>
      <section className="card dashboard-welcome">
        <div>
          <p className="eyebrow">Operations overview</p>
          <h2>Claim control center</h2>
          <p className="hero-copy">Monitor submissions, asynchronous processing, policy verification and cases that need human attention.</p>
        </div>
        <Link className="button-primary nav-button" to="/admin/review">Open review queue</Link>
      </section>

      <SectionCard title="Claim Control Overview" subtitle="Live processing metrics">
        <div className="dashboard-grid">
          <article className="metric-card"><p className="eyebrow">Total claims</p><h3>{claims.length}</h3><p className="metric-label">All submissions</p></article>
          <article className="metric-card"><p className="eyebrow">Processing</p><h3>{processingClaims}</h3><p className="metric-label">Async OCR queue</p></article>
          <article className="metric-card"><p className="eyebrow">Approved</p><h3>{approvedClaims}</h3><p className="metric-label">Completed claims</p></article>
          <article className="metric-card"><p className="eyebrow">Policy verified</p><h3>{policyVerifiedClaims}</h3><p className="metric-label">RAG checks completed</p></article>
        </div>
      </SectionCard>

      <SectionCard title="Agentic Decision Metrics" subtitle="Measured from policy verification audit records">
        <div className="dashboard-grid">
          <article className="metric-card"><p className="eyebrow">Autonomous rate</p><h3>{decisionMetrics ? `${decisionMetrics.autonomous_decision_rate_percent}%` : '—'}</h3><p className="metric-label">Approved + rejected automatically</p></article>
          <article className="metric-card"><p className="eyebrow">Manual reduction</p><h3>{decisionMetrics ? `${decisionMetrics.manual_review_reduction_percent}%` : '—'}</h3><p className="metric-label">Against all-manual baseline</p></article>
          <article className="metric-card"><p className="eyebrow">Human review</p><h3>{decisionMetrics?.human_review ?? '—'}</h3><p className="metric-label">Escalated decisions</p></article>
          <article className="metric-card"><p className="eyebrow">Avg confidence</p><h3>{decisionMetrics ? `${(decisionMetrics.average_confidence * 100).toFixed(1)}%` : '—'}</h3><p className="metric-label">Decision confidence</p></article>
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
