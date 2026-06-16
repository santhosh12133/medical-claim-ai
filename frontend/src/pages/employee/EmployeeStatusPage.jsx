import { useEffect, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function EmployeeStatusPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  return (
    <SectionCard title="Claim Status" subtitle="Employee side">
      <div className="stack">
        {claims.length ? claims.map((claim) => (
          <article key={claim.id} className="status-row">
            <div>
              <h3>{claim.employee_name}</h3>
              <p>{claim.hospital_name || 'Unknown hospital'}</p>
              <p>{claim.treatment || 'Unknown treatment'}</p>
              <p>{claim.policy_decision ? `Policy: ${claim.policy_decision}` : 'Policy: Not verified'}</p>
            </div>
            <div className={`status-pill status-${String(claim.status || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
              {claim.status}
            </div>
          </article>
        )) : <p className="hint">No claims found yet.</p>}
      </div>
    </SectionCard>
  );
}
