import { useEffect, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

const statusClass = (status) => `status-pill status-${String(status || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

export function EmployeeStatusPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const stage = (claim) => {
    const value = String(claim.status || '').toLowerCase();
    if (value === 'approved' || value === 'rejected') return 3;
    if (claim.policy_decision) return 2;
    return 1;
  };

  return (
    <SectionCard title="Claim Status" subtitle="Track every claim through processing">
      <div className="status-list">
        {claims.length ? claims.map((claim) => {
          const current = stage(claim);
          return <article key={claim.id} className="status-card">
            <div className="status-card__header"><div><p className="eyebrow">Claim #{claim.id}</p><h3>{claim.treatment || 'Medical claim'}</h3><p>{claim.hospital_name || 'Unknown hospital'}</p></div><span className={statusClass(claim.status)}>{claim.status || 'Pending'}</span></div>
            <div className="timeline">
              {['Submitted', 'AI + Policy Review', 'Final Decision'].map((label, index) => <div key={label} className={`timeline-step ${current > index ? 'timeline-step--done' : current === index + 1 ? 'timeline-step--current' : ''}`}><span>{current > index ? '✓' : index + 1}</span><small>{label}</small></div>)}
            </div>
            <div className="status-summary"><span>Claim amount <strong>₹{claim.amount ?? '—'}</strong></span><span>Policy <strong>{claim.policy_decision || 'Under review'}</strong></span></div>
            {claim.policy_reason ? <p className="hint">{claim.policy_reason}</p> : null}
          </article>;
        }) : <div className="empty-state"><div className="empty-state__icon">✓</div><h3>No claims to track</h3><p>Your submitted claims will appear here.</p></div>}
      </div>
    </SectionCard>
  );
}
