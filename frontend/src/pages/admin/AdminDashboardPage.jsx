import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';
import { FlagList, formatMoney } from '../../components/ui';

export function AdminDashboardPage() {
  const [claims, setClaims] = useState([]);
  const [decisionMetrics, setDecisionMetrics] = useState(null);
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
    api.get('/rag/metrics/decisions').then((response) => setDecisionMetrics(response.data)).catch(() => setDecisionMetrics(null));
    api.get('/claims/summary').then((response) => setSummary(response.data)).catch(() => setSummary(null));
  }, []);

  const closed = new Set(['Approved', 'Partially Approved', 'Rejected']);
  const pendingClaims = claims.filter((claim) => !closed.has(claim.status)).length;
  const rejectedClaims = claims.filter((claim) => claim.status === 'Rejected').length;
  const processingClaims = claims.filter((claim) => claim.status === 'Processing').length;
  const policyVerifiedClaims = claims.filter((claim) => claim.policy_decision).length;
  const approvedClaims = claims.filter((claim) => claim.status === 'Approved' || claim.status === 'Partially Approved').length;
  const flaggedClaims = summary?.flagged_claims ?? claims.filter((claim) => claim.risk_flags_json?.length).length;

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
          <article className="metric-card"><p className="eyebrow">Approved</p><h3>{approvedClaims}</h3><p className="metric-label">{summary ? `${formatMoney(summary.total_approved_amount)} reimbursed` : 'Completed claims'}</p></article>
          <article className="metric-card"><p className="eyebrow">Policy verified</p><h3>{policyVerifiedClaims}</h3><p className="metric-label">RAG checks completed</p></article>
        </div>
      </SectionCard>

      <SectionCard title="Agentic Decision Metrics" subtitle="Measured from policy verification audit records">
        <div className="dashboard-grid">
          <article className="metric-card"><p className="eyebrow">Autonomous rate</p><h3>{decisionMetrics ? `${decisionMetrics.autonomous_decision_rate_percent}%` : '—'}</h3><p className="metric-label">{decisionMetrics ? `${decisionMetrics.auto_approved} approved · ${decisionMetrics.auto_partially_approved} partial · ${decisionMetrics.auto_rejected} rejected` : 'Decided automatically'}</p></article>
          <article className="metric-card"><p className="eyebrow">Avg latency</p><h3>{decisionMetrics?.average_latency_ms != null ? `${Math.round(decisionMetrics.average_latency_ms)} ms` : '—'}</h3><p className="metric-label">Retrieval → decision</p></article>
          <article className="metric-card"><p className="eyebrow">Human review</p><h3>{decisionMetrics?.human_review ?? '—'}</h3><p className="metric-label">Escalated decisions</p></article>
          <article className="metric-card"><p className="eyebrow">Avg confidence</p><h3>{decisionMetrics ? `${(decisionMetrics.average_confidence * 100).toFixed(1)}%` : '—'}</h3><p className="metric-label">Decision confidence</p></article>
        </div>
      </SectionCard>

      <SectionCard title="Processing health" subtitle="Current queue signals">
        <div className="health-grid">
          <div className="health-item"><span className="health-dot health-dot--green" /><div><strong>Policy verification</strong><p>{policyVerifiedClaims} claims have policy evidence.</p></div></div>
          <div className="health-item"><span className="health-dot health-dot--amber" /><div><strong>Human review</strong><p>{pendingClaims} claims are still in the queue.</p></div></div>
          <div className="health-item"><span className="health-dot health-dot--red" /><div><strong>Risk flags</strong><p>{flaggedClaims} claims carry fraud or quality flags · {rejectedClaims} rejected.</p></div></div>
        </div>
      </SectionCard>

      {decisionMetrics?.top_flags && Object.keys(decisionMetrics.top_flags).length ? (
        <SectionCard title="Most common decision flags" subtitle="Why claims go to humans">
          <FlagList flags={Object.keys(decisionMetrics.top_flags)} />
          <ul className="flag-counts">
            {Object.entries(decisionMetrics.top_flags).map(([flag, count]) => <li key={flag}><span>{flag}</span><strong>{count}</strong></li>)}
          </ul>
        </SectionCard>
      ) : null}

      {summary?.recent_activity?.length ? (
        <SectionCard title="Recent activity" subtitle="Claim timeline events">
          <ol className="trace">
            {summary.recent_activity.map((event) => (
              <li key={`${event.claim_id}-${event.created_at}-${event.event_type}`}>
                <strong>#{event.claim_id}</strong> {event.message} <span className="muted-text">{event.created_at ? new Date(event.created_at).toLocaleString() : ''}</span>
              </li>
            ))}
          </ol>
        </SectionCard>
      ) : null}
    </>
  );
}
