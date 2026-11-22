import { useCallback, useEffect, useState } from 'react';

import { api } from '../../api';
import { ExtractedFields } from '../../components/ClaimViews';
import { EvidencePanel } from '../../components/EvidencePanel';
import { Icon } from '../../components/Icon';
import {
  EmptyState, FlagList, PageHeader, Panel, Stamp, StatusBadge, Toast, errorMessage, formatDate, formatMoney,
} from '../../components/ui';
import { OPEN_STATUSES } from '../../layouts/AdminLayout';

const auditToVerification = (audit) => ({
  status: audit.decision,
  approved_amount: audit.approved_amount,
  confidence: Number(audit.confidence),
  policy_source: audit.policy_source,
  policy_used: audit.policy_used,
  reason: audit.reason,
  decision_trace: audit.decision_trace_json,
  retrieved_policies: audit.retrieved_chunks_json,
  flags: audit.risk_flags_json,
  extracted_rule: audit.extracted_rules_json,
  latency_ms: audit.latency_ms,
  autonomous: audit.auto_decision !== 'human',
  confidence_breakdown: {},
});

const TOOL_NAMES = {
  run_ocr: 'Read the bill',
  extract_fields: 'Extracted the details',
  infer_treatment: 'Worked out the treatment',
  check_risks: 'Checked for red flags',
  verify_policy: 'Checked the policy',
  escalate_to_human: 'Sent to a reviewer',
  complete: 'Finished',
};

function AgentSteps({ claimId, refreshKey }) {
  const [run, setRun] = useState(null);

  useEffect(() => {
    api.get(`/claims/${claimId}/events`)
      .then((response) => {
        const latest = [...response.data].reverse().find((event) => event.event_type === 'AGENT_RUN');
        setRun(latest ? JSON.parse(latest.metadata_json || '{}') : null);
      })
      .catch(() => setRun(null));
  }, [claimId, refreshKey]);

  if (!run?.steps?.length) return null;
  return (
    <details className="disclosure">
      <summary>How this claim was processed ({run.steps.length} steps{run.planner === 'llm' ? ', planned by AI' : ''})</summary>
      {run.escalation_reason ? <p className="disclosure__lead">Sent for review: {run.escalation_reason}</p> : null}
      <ol className="steps">
        {run.steps.map((step) => (
          <li key={step.step} className={step.status === 'error' ? 'steps__item--failed' : ''}>
            <strong>{TOOL_NAMES[step.tool] || step.tool}</strong>
            <span>{step.rationale}</span>
            {step.status === 'error' ? <span className="steps__note">Failed after {step.attempts} attempts</span> : null}
            {step.attempts > 1 && step.status !== 'error' ? <span className="steps__note">Succeeded on attempt {step.attempts}</span> : null}
          </li>
        ))}
      </ol>
    </details>
  );
}

function ReviewCard({ claim, onChanged, notify }) {
  const [open, setOpen] = useState(false);
  const [verification, setVerification] = useState(null);
  const [busy, setBusy] = useState('');
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');

  const recommended = ['Approved', 'Partially Approved'].includes(claim.policy_decision) ? claim.policy_approved_amount : claim.amount;

  const loadLatestAudit = useCallback(async () => {
    try {
      const response = await api.get(`/rag/claims/${claim.id}/verifications`);
      if (response.data.length) setVerification(auditToVerification(response.data[0]));
    } catch {
      /* no policy check yet */
    }
  }, [claim.id]);

  useEffect(() => {
    if (open && !verification && claim.policy_decision) loadLatestAudit();
  }, [open, verification, claim.policy_decision, loadLatestAudit]);

  const run = async (label, request, success) => {
    setBusy(label);
    try {
      success(await request());
    } catch (actionError) {
      notify('error', `${label} didn’t work`, errorMessage(actionError));
    } finally {
      setBusy('');
    }
  };

  const recheck = () => run('Policy check', () => api.post(`/rag/claims/${claim.id}/verify`), (response) => {
    setVerification(response.data);
    setOpen(true);
    notify('success', 'Policy checked again', `${response.data.status}. ${response.data.reason}`);
    onChanged();
  });

  const approve = () => run('Approval', () => api.patch(`/claims/${claim.id}/approve`, {
    approved_amount: amount ? Number(amount) : undefined,
    notes: notes || undefined,
  }), (response) => {
    notify('success', `Claim #${claim.id} approved`, `${formatMoney(response.data.claim.final_approved_amount)} for ${claim.employee_name}.`);
    onChanged();
  });

  const reject = () => run('Rejection', () => api.patch(`/claims/${claim.id}/reject`, { notes: notes || undefined }), () => {
    notify('success', `Claim #${claim.id} rejected`, notes ? `Reason sent: ${notes}` : 'No reason was added.');
    onChanged();
  });

  const reprocess = () => run('Re-reading', () => api.post(`/claims/${claim.id}/reprocess`), () => {
    notify('success', `Claim #${claim.id} is being read again`, 'The bill will be read and checked again in a moment.');
    onChanged();
  });

  const viewBill = () => run('Opening the bill', () => api.get(`/claims/${claim.id}/document`, { responseType: 'blob' }), (response) => {
    const url = URL.createObjectURL(response.data);
    window.open(url, '_blank', 'noopener');
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  });

  const processing = ['queued', 'processing'].includes(claim.processing_status);

  return (
    <article className={`review-card ${claim.risk_flags_json?.length ? 'review-card--flagged' : ''}`}>
      <div className="review-card__head">
        <div className="review-card__who">
          <h3>{claim.employee_name}</h3>
          <p>{processing && !claim.treatment ? 'New claim' : `${claim.treatment || 'Treatment not read'}, ${claim.hospital_name || 'hospital not read'}`}</p>
          <p className="review-card__facts">
            <span>Claim #{claim.id}</span>
            {claim.claim_date ? <span>Bill dated {formatDate(claim.claim_date)}</span> : null}
            {claim.amount != null ? <span className="num">{formatMoney(claim.amount)} claimed</span> : null}
            {processing ? <span>The bill is still being read</span> : null}
          </p>
          <FlagList flags={claim.risk_flags_json} />
          {claim.processing_error ? <p className="form-error"><Icon name="alert" size={16} />{claim.processing_error}</p> : null}
        </div>
        <div className="review-card__verdict">
          {claim.policy_decision ? (
            <>
              <span className="review-card__verdict-label">Policy check recommends</span>
              <Stamp status={claim.policy_decision} amount={claim.policy_approved_amount} compact />
            </>
          ) : <StatusBadge status={claim.status} />}
        </div>
      </div>

      <div className="review-card__actions">
        <button type="button" className="button button--secondary" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          {open ? 'Hide details' : 'Review details'}
        </button>
        <button type="button" className="button button--ghost" onClick={viewBill} disabled={Boolean(busy)}><Icon name="file" />View bill</button>
        <button type="button" className="button button--ghost" onClick={recheck} disabled={Boolean(busy) || processing || !claim.treatment}>
          <Icon name="policies" />{busy === 'Policy check' ? 'Checking…' : 'Re-check policy'}
        </button>
        <button type="button" className="button button--ghost" onClick={reprocess} disabled={Boolean(busy) || processing}>
          <Icon name="refresh" />Re-read bill
        </button>
      </div>

      {open ? (
        <div className="review-card__body">
          <ExtractedFields claim={claim} />
          {claim.declared_amount != null && claim.amount != null && Number(claim.declared_amount) !== Number(claim.amount) ? (
            <p className="note">The employee entered {formatMoney(claim.declared_amount)}; the bill total reads {formatMoney(claim.amount)}.</p>
          ) : null}
          {verification ? <EvidencePanel verification={verification} />
            : <p className="hint">This claim hasn’t been checked against a policy yet. Use “Re-check policy” to run it.</p>}
          <AgentSteps claimId={claim.id} refreshKey={claim.updated_at} />

          <div className="decision-form">
            <h4>Your decision</h4>
            <div className="form-row">
              <label className="field">
                <span className="field__label">Amount to reimburse</span>
                <input type="number" inputMode="decimal" min="1" step="0.01" value={amount}
                  placeholder={recommended != null ? `${formatMoney(recommended)} recommended` : 'Full bill amount'}
                  onChange={(event) => setAmount(event.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Note to the employee <span className="field__optional">optional</span></span>
                <input type="text" maxLength={2000} value={notes} placeholder="Shown to the employee and kept in the audit trail"
                  onChange={(event) => setNotes(event.target.value)} />
              </label>
            </div>
            <div className="button-row">
              <button type="button" className="button button--primary" onClick={approve} disabled={Boolean(busy) || processing}>
                <Icon name="check" />Approve
              </button>
              <button type="button" className="button button--danger" onClick={reject} disabled={Boolean(busy) || processing}>Reject</button>
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function AdminReviewPage() {
  const [claims, setClaims] = useState(null);
  const [toast, setToast] = useState(null);
  const [onlyFlagged, setOnlyFlagged] = useState(false);

  const load = useCallback(async () => {
    const response = await api.get('/claims');
    setClaims(response.data.filter((claim) => OPEN_STATUSES.has(claim.status)));
  }, []);

  useEffect(() => { load().catch(() => setClaims([])); }, [load]);

  const notify = (type, title, message) => setToast({ type, title, message });
  const closeToast = useCallback(() => setToast(null), []);
  const list = claims || [];
  const flagged = list.filter((claim) => claim.risk_flags_json?.length);
  const shown = onlyFlagged ? flagged : list;

  return (
    <>
      <PageHeader title="Review queue"
        description="Claims the automatic checks couldn’t settle on their own. Each one shows why." />
      <Toast toast={toast} onClose={closeToast} />

      <Panel title={null}>
        <div className="toolbar">
          <div className="segmented" role="tablist" aria-label="Filter the queue">
            <button type="button" role="tab" aria-selected={!onlyFlagged}
              className={`segmented__option ${!onlyFlagged ? 'segmented__option--active' : ''}`} onClick={() => setOnlyFlagged(false)}>
              All waiting <span className="segmented__count">{list.length}</span>
            </button>
            <button type="button" role="tab" aria-selected={onlyFlagged}
              className={`segmented__option ${onlyFlagged ? 'segmented__option--active' : ''}`} onClick={() => setOnlyFlagged(true)}>
              Red flags <span className="segmented__count">{flagged.length}</span>
            </button>
          </div>
        </div>

        {claims === null ? <p className="loading-line">Loading the queue…</p> : shown.length ? (
          <div className="review-list">
            {shown.map((claim) => <ReviewCard key={claim.id} claim={claim} onChanged={() => load().catch(() => undefined)} notify={notify} />)}
          </div>
        ) : (
          <EmptyState icon="check" title={onlyFlagged ? 'No flagged claims' : 'Nothing to review'}>
            {onlyFlagged ? 'Claims with red flags will appear here.' : 'New claims that need a reviewer will appear here.'}
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
