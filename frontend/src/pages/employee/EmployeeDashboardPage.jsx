import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { ClaimRow } from '../../components/ClaimViews';
import { Icon } from '../../components/Icon';
import { EmptyState, PageHeader, Panel, formatMoney, isFinal } from '../../components/ui';

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

export function EmployeeDashboardPage() {
  const { user } = useAuth();
  const [claims, setClaims] = useState(null);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const list = claims || [];
  const approved = list.filter((claim) => ['Approved', 'Partially Approved'].includes(claim.status));
  const inProgress = list.filter((claim) => !isFinal(claim.status)).length;
  const reimbursed = approved.reduce((total, claim) => total + Number(claim.final_approved_amount ?? 0), 0);
  const firstName = String(user?.full_name || '').split(' ')[0];

  return (
    <>
      <PageHeader
        title={`${greeting()}${firstName ? `, ${firstName}` : ''}`}
        description="Submit a hospital bill or check where your claims stand."
        actions={<Link className="button button--primary" to="/employee/upload"><Icon name="submit" />Submit a bill</Link>}
      />

      <dl className="figures">
        <div className="metric-card"><dt>Claims submitted</dt><dd>{list.length}</dd></div>
        <div className="metric-card"><dt>In progress</dt><dd>{inProgress}</dd></div>
        <div className="metric-card"><dt>Approved</dt><dd>{approved.length}</dd></div>
        <div className="metric-card"><dt>Reimbursed</dt><dd>{formatMoney(reimbursed)}</dd></div>
      </dl>

      <div className="split">
        <Panel title="Recent claims" actions={list.length ? <Link className="text-link" to="/employee/claims">See all claims</Link> : null}>
          {claims === null ? <p className="loading-line">Loading claims…</p> : list.length ? (
            <div className="claim-list">
              {list.slice(0, 5).map((claim) => <ClaimRow key={claim.id} claim={claim} />)}
            </div>
          ) : (
            <EmptyState title="No claims yet" action={<Link className="button button--primary" to="/employee/upload">Submit your first bill</Link>}>
              Upload a hospital bill as a PDF or photo. You’ll see the result here.
            </EmptyState>
          )}
        </Panel>

        <Panel title="How claims are decided" className="panel--quiet">
          <ol className="process">
            <li><strong>You upload the bill.</strong> A PDF, scan or clear photo, up to 10 MB.</li>
            <li><strong>It’s read and checked.</strong> The hospital, date, treatment and total are matched to your reimbursement policy.</li>
            <li><strong>It’s decided.</strong> Straightforward claims are approved or rejected straight away. If something needs a second look, a reviewer decides.</li>
          </ol>
          <p className="panel__footnote">Not sure a treatment is covered? <Link to="/employee/assistant">Ask a coverage question</Link>.</p>
        </Panel>
      </div>
    </>
  );
}
