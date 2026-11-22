import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { Icon } from '../../components/Icon';
import { EmptyState, PageHeader, Panel, flagLabel, formatDateTime, formatMoney } from '../../components/ui';
import { OPEN_STATUSES } from '../../layouts/AdminLayout';

export function AdminDashboardPage() {
  const [claims, setClaims] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
    api.get('/rag/metrics/decisions').then((response) => setMetrics(response.data)).catch(() => setMetrics(null));
    api.get('/claims/summary').then((response) => setSummary(response.data)).catch(() => setSummary(null));
  }, []);

  const waiting = claims.filter((claim) => OPEN_STATUSES.has(claim.status));
  const flagged = waiting.filter((claim) => claim.risk_flags_json?.length).length;
  const approved = claims.filter((claim) => ['Approved', 'Partially Approved'].includes(claim.status));
  const rejected = claims.filter((claim) => claim.status === 'Rejected').length;
  const topFlags = Object.entries(metrics?.top_flags || {}).filter(([flag]) => flag !== 'BLOCKING_FLAG');
  const maxFlag = Math.max(1, ...topFlags.map(([, count]) => count));
  const decided = metrics ? metrics.auto_approved + metrics.auto_partially_approved + metrics.auto_rejected : 0;

  return (
    <>
      <PageHeader
        title="Overview"
        description="What’s waiting for you, and how the automatic checks are doing."
        actions={<Link className="button button--primary" to="/admin/review"><Icon name="queue" />Open review queue</Link>}
      />

      <dl className="figures">
        <div className="metric-card metric-card--attention"><dt>Waiting for review</dt><dd>{waiting.length}</dd>
          <span>{flagged ? `${flagged} with red flags` : 'None flagged'}</span></div>
        <div className="metric-card"><dt>Approved</dt><dd>{approved.length}</dd>
          <span>{summary ? `${formatMoney(summary.total_approved_amount)} reimbursed` : ' '}</span></div>
        <div className="metric-card"><dt>Rejected</dt><dd>{rejected}</dd><span>{claims.length} claims in total</span></div>
        <div className="metric-card"><dt>Decided automatically</dt>
          <dd>{metrics && metrics.total_verifications ? `${Math.round(metrics.autonomous_decision_rate_percent)}%` : '—'}</dd>
          <span>{metrics ? `${decided} of ${metrics.total_verifications} policy checks` : ' '}</span></div>
      </dl>

      <div className="split split--even">
        <Panel title="Why claims were sent for review" description="Red flags raised by the checks, most common first.">
          {topFlags.length ? (
            <ul className="bars">
              {topFlags.map(([flag, count]) => (
                <li key={flag}>
                  <span className="bars__label">{flagLabel(flag)}</span>
                  <span className="bars__track"><span className="bars__fill" style={{ width: `${(count / maxFlag) * 100}%` }} /></span>
                  <span className="bars__value">{count}</span>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="check" title="No red flags yet">Flags appear here once claims have been checked.</EmptyState>}
        </Panel>

        <Panel title="Automatic decisions" description="From the policy checks recorded so far.">
          {metrics && metrics.total_verifications ? (
            <dl className="stat-list">
              <div><dt>Approved</dt><dd>{metrics.auto_approved}</dd></div>
              <div><dt>Partially approved</dt><dd>{metrics.auto_partially_approved}</dd></div>
              <div><dt>Rejected</dt><dd>{metrics.auto_rejected}</dd></div>
              <div><dt>Sent to a reviewer</dt><dd>{metrics.human_review}</dd></div>
              <div><dt>Average confidence</dt><dd>{(metrics.average_confidence * 100).toFixed(0)}%</dd></div>
              <div><dt>Average check time</dt><dd>{metrics.average_latency_ms != null ? `${(metrics.average_latency_ms / 1000).toFixed(1)} s` : '—'}</dd></div>
            </dl>
          ) : <EmptyState icon="policies" title="No policy checks yet">Results appear after the first claim is checked.</EmptyState>}
        </Panel>
      </div>

      <Panel title="Recent activity">
        {summary?.recent_activity?.length ? (
          <ol className="activity">
            {summary.recent_activity.map((event) => (
              <li key={`${event.claim_id}-${event.created_at}-${event.event_type}`}>
                <span className="activity__claim">Claim #{event.claim_id}</span>
                <span className="activity__message">{event.message}</span>
                <time className="activity__time">{formatDateTime(event.created_at)}</time>
              </li>
            ))}
          </ol>
        ) : <EmptyState icon="claims" title="Nothing yet">Submitted and decided claims appear here.</EmptyState>}
      </Panel>
    </>
  );
}
