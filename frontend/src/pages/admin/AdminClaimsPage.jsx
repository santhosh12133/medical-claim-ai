import { useEffect, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function AdminClaimsPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  return (
    <SectionCard title="Claims List" subtitle="Admin side">
      <div className="list-grid">
        {claims.length ? claims.map((claim) => (
          <article key={claim.id} className="list-item">
            <h3>{claim.employee_name}</h3>
            <p>{claim.hospital_name || 'Unknown hospital'}</p>
            <p>Treatment: {claim.treatment || 'N/A'}</p>
            <p>Amount: {claim.amount ?? 'N/A'}</p>
            <p>Policy: {claim.policy_decision || 'Not verified'}</p>
            {claim.policy_reason ? <p>{claim.policy_reason}</p> : null}
            <p>Status: {claim.status}</p>
          </article>
        )) : <p className="hint">No claims in the system yet.</p>}
      </div>
    </SectionCard>
  );
}
