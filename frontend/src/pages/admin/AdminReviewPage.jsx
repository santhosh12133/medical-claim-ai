import { useEffect, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function AdminReviewPage() {
  const [claims, setClaims] = useState([]);
  const [toast, setToast] = useState(null);
  const [policyLoadingId, setPolicyLoadingId] = useState(null);

  const pendingStatuses = new Set(['Pending', 'Pending Review', 'Needs Attention']);

  const loadClaims = async () => {
    const response = await api.get('/claims');
    setClaims(response.data.filter((claim) => pendingStatuses.has(claim.status)));
  };

  useEffect(() => {
    loadClaims().catch(() => setClaims([]));
  }, []);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }

    const timer = window.setTimeout(() => setToast(null), 2500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const handleAction = async (claimId, action) => {
    const nextStatus = action === 'approve' ? 'approved' : 'rejected';
    const title = action === 'approve' ? 'Claim approved' : 'Claim rejected';
    const message = action === 'approve'
      ? 'The claim was successfully approved.'
      : 'The claim was successfully rejected.';

    await api.patch(`/claims/${claimId}/${action}`);
    setClaims((currentClaims) => currentClaims.filter((claim) => claim.id !== claimId));
    setToast({
      type: nextStatus,
      title,
      message,
    });
  };

  const handlePolicyVerify = async (claimId) => {
    setPolicyLoadingId(claimId);
    try {
      const response = await api.post(`/rag/claims/${claimId}/verify`);
      await loadClaims();
      setToast({
        type: response.data.status === 'Rejected' ? 'rejected' : 'approved',
        title: 'Policy verification complete',
        message: `${response.data.status}: ${response.data.reason}`,
      });
    } catch (verificationError) {
      setToast({
        type: 'rejected',
        title: 'Policy verification failed',
        message: verificationError.response?.data?.detail || 'Unable to verify this claim against policy.',
      });
    } finally {
      setPolicyLoadingId(null);
    }
  };

  return (
    <SectionCard title="Review Claims" subtitle="Admin side">
      {toast ? (
        <div className={`toast toast--${toast.type}`} role="status" aria-live="polite">
          <div className="toast__icon">{toast.type === 'approved' ? '✓' : '!'}</div>
          <div className="toast__content">
            <p className="toast__title">{toast.title}</p>
            <p className="toast__message">{toast.message}</p>
          </div>
          <button type="button" className="toast__close" onClick={() => setToast(null)} aria-label="Close notification">
            ×
          </button>
        </div>
      ) : null}
      <div className="stack">
        {claims.length ? claims.map((claim) => (
          <article key={claim.id} className="admin-row">
            <div>
              <h3>{claim.employee_name}</h3>
              <p>{claim.hospital_name || 'Unknown hospital'}</p>
              <p>Treatment: {claim.treatment || 'N/A'}</p>
              <p>Amount: {claim.amount ?? 'N/A'}</p>
              <p>Policy: {claim.policy_decision || 'Not verified'}</p>
              <p className="hint">{claim.validation_message || 'Waiting for review'}</p>
            </div>
            <div className="button-row">
              <button type="button" className="secondary" onClick={() => handlePolicyVerify(claim.id)} disabled={policyLoadingId === claim.id}>
                {policyLoadingId === claim.id ? 'Verifying...' : 'Verify Policy'}
              </button>
              <button type="button" onClick={() => handleAction(claim.id, 'approve')}>Approve</button>
              <button type="button" className="secondary" onClick={() => handleAction(claim.id, 'reject')}>Reject</button>
            </div>
          </article>
        )) : <p className="hint">No claims in the system yet.</p>}
      </div>
    </SectionCard>
  );
}
