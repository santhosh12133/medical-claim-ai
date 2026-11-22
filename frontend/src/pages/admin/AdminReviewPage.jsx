import { useCallback, useEffect, useState } from 'react';

import { api } from '../../api';
import { EvidencePanel } from '../../components/EvidencePanel';
import { SectionCard } from '../../components/SectionCard';
import { FlagList, errorMessage, formatMoney, statusClass } from '../../components/ui';

const PENDING_STATUSES = new Set(['Pending', 'Pending Review', 'Needs Attention', 'Processing']);

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

function ReviewCard({ claim, onChanged, notify }) {
  const [open, setOpen] = useState(false);
  const [verification, setVerification] = useState(null);
  const [busy, setBusy] = useState('');
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');

  const recommended = claim.policy_decision && ['Approved', 'Partially Approved'].includes(claim.policy_decision)
    ? claim.policy_approved_amount
    : claim.amount;

  const loadLatestAudit = useCallback(async () => {
    try {
      const response = await api.get(`/rag/claims/${claim.id}/verifications`);
      if (response.data.length) setVerification(auditToVerification(response.data[0]));
    } catch {
      /* no audit yet */
    }
  }, [claim.id]);

  useEffect(() => {
    if (open && !verification && claim.policy_decision) loadLatestAudit();
  }, [open, verification, claim.policy_decision, loadLatestAudit]);

  const run = async (label, request, success) => {
    setBusy(label);
    try {
      const response = await request();
      success(response);
    } catch (actionError) {
      notify('rejected', `${label} failed`, errorMessage(actionError));
    } finally {
      setBusy('');
    }
  };

  const verify = () => run('Policy verification', () => api.post(`/rag/claims/${claim.id}/verify`), (response) => {
    setVerification(response.data);
    setOpen(true);
    notify(response.data.status === 'Rejected' ? 'rejected' : 'approved', 'Policy verification complete',
      `${response.data.status}: ${response.data.reason}`);
    onChanged(false);
  });

  const approve = () => run('Approval', () => api.patch(`/claims/${claim.id}/approve`, {
    approved_amount: amount ? Number(amount) : undefined,
    notes: notes || undefined,
  }), (response) => {
    notify('approved', response.data.message, `Claim #${claim.id} for ${formatMoney(response.data.claim.final_approved_amount)}`);
    onChanged(true);
  });

  const reject = () => run('Rejection', () => api.patch(`/claims/${claim.id}/reject`, { notes: notes || undefined }), () => {
    notify('rejected', 'Claim rejected', `Claim #${claim.id} was rejected.`);
    onChanged(true);
  });

  const reprocess = () => run('Reprocess', () => api.post(`/claims/${claim.id}/reprocess`), () => {
    notify('approved', 'Claim re-queued', 'OCR and policy verification will run again shortly.');
    onChanged(false);
  });

  const viewDocument = () => run('Document download', () => api.get(`/claims/${claim.id}/document`, { responseType: 'blob' }),
    (response) => {
      const url = URL.createObjectURL(response.data);
      window.open(url, '_blank', 'noopener');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    });

  const processing = ['queued', 'processing'].includes(claim.processing_status);

  return (
    <article className="review-card">
      <div className="review-card__head">
        <div>
          <p className="eyebrow">Claim #{claim.id} · {claim.policy_category || 'Uncategorised'}</p>
          <h3>{claim.employee_name} — {claim.treatment || 'Treatment not read'}</h3>
          <p className="muted-text">
            {claim.hospital_name || 'Unknown hospital'} · {claim.claim_date || 'no date'} · claimed {formatMoney(claim.amount)}
            {claim.patient_name ? ` · patient ${claim.patient_name}` : ''}
          </p>
          <FlagList flags={claim.risk_flags_json} />
          {claim.processing_error ? <p className="error-text">{claim.processing_error}</p> : null}
        </div>
        <div className="review-card__status">
          <span className={statusClass(claim.status)}>{claim.status}</span>
          {claim.policy_decision ? (
            <span className="muted-text">AI: {claim.policy_decision} {formatMoney(claim.policy_approved_amount)}</span>
          ) : <span className="muted-text">{claim.validation_message || 'Not verified'}</span>}
        </div>
      </div>

      <div className="button-row">
        <button type="button" className="secondary" onClick={() => setOpen((value) => !value)}>{open ? 'Hide details' : 'Review details'}</button>
        <button type="button" className="secondary" onClick={verify} disabled={Boolean(busy) || processing || !claim.treatment}>
          {busy === 'Policy verification' ? 'Verifying…' : claim.policy_decision ? 'Re-verify policy' : 'Verify policy'}
        </button>
        <button type="button" className="secondary" onClick={viewDocument} disabled={Boolean(busy)}>View bill</button>
        <button type="button" className="secondary" onClick={reprocess} disabled={Boolean(busy) || processing}>Reprocess</button>
      </div>

      {open ? (
        <div className="review-card__body">
          {verification ? <EvidencePanel verification={verification} /> : <p className="hint">No policy verification yet. Run “Verify policy” to retrieve evidence.</p>}
          <div className="decision-form">
            <label>
              Approved amount
              <input type="number" min="1" step="0.01" placeholder={recommended ? `Recommended ${recommended}` : 'Full amount'}
                value={amount} onChange={(event) => setAmount(event.target.value)} />
            </label>
            <label>
              Reviewer notes
              <input type="text" maxLength={2000} placeholder="Reason for the decision (shown in the audit trail)"
                value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
            <div className="button-row">
              <button type="button" onClick={approve} disabled={Boolean(busy) || processing}>Approve</button>
              <button type="button" className="secondary danger" onClick={reject} disabled={Boolean(busy) || processing}>Reject</button>
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function AdminReviewPage() {
  const [claims, setClaims] = useState([]);
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadClaims = useCallback(async () => {
    const response = await api.get('/claims');
    setClaims(response.data.filter((claim) => PENDING_STATUSES.has(claim.status)));
  }, []);

  useEffect(() => {
    loadClaims().catch(() => setClaims([])).finally(() => setLoading(false));
  }, [loadClaims]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const notify = (type, title, message) => setToast({ type, title, message });
  const onChanged = () => loadClaims().catch(() => undefined);

  const flagged = claims.filter((claim) => claim.risk_flags_json?.length).length;

  return (
    <SectionCard title="Review Queue" subtitle={`${claims.length} open · ${flagged} flagged`}>
      {toast ? (
        <div className={`toast toast--${toast.type}`} role="status" aria-live="polite">
          <div className="toast__icon">{toast.type === 'approved' ? '✓' : '!'}</div>
          <div className="toast__content">
            <p className="toast__title">{toast.title}</p>
            <p className="toast__message">{toast.message}</p>
          </div>
          <button type="button" className="toast__close" onClick={() => setToast(null)} aria-label="Close notification">×</button>
        </div>
      ) : null}
      <div className="stack">
        {loading ? <p className="hint">Loading claims…</p> : null}
        {!loading && !claims.length ? <p className="hint">The review queue is empty.</p> : null}
        {claims.map((claim) => <ReviewCard key={claim.id} claim={claim} onChanged={onChanged} notify={notify} />)}
      </div>
    </SectionCard>
  );
}
