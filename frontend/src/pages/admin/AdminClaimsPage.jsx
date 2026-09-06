import { useEffect, useMemo, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

const statusClass = (status) => `status-pill status-${String(status || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

export function AdminClaimsPage() {
  const [claims, setClaims] = useState([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All');

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const filteredClaims = useMemo(() => claims.filter((claim) => {
    const haystack = [claim.employee_name, claim.hospital_name, claim.treatment, claim.policy_decision].join(' ').toLowerCase();
    return haystack.includes(query.toLowerCase()) && (status === 'All' || claim.status === status);
  }), [claims, query, status]);

  const statuses = ['All', ...new Set(claims.map((claim) => claim.status).filter(Boolean))];

  return (
    <SectionCard title="All Claims" subtitle={`${filteredClaims.length} of ${claims.length} claims` }>
      <div className="toolbar">
        <input aria-label="Search all claims" placeholder="Search employee, hospital or treatment..." value={query} onChange={(event) => setQuery(event.target.value)} />
        <select aria-label="Filter claims by status" value={status} onChange={(event) => setStatus(event.target.value)}>
          {statuses.map((item) => <option key={item}>{item}</option>)}
        </select>
      </div>
      <div className="table-wrap">
        <table className="claims-table">
          <thead><tr><th>Employee</th><th>Treatment / Hospital</th><th>Amount</th><th>AI Policy</th><th>Status</th></tr></thead>
          <tbody>
            {filteredClaims.map((claim) => (
              <tr key={claim.id}>
                <td><strong>{claim.employee_name || 'Unknown'}</strong><small>Claim #{claim.id}</small></td>
                <td><strong>{claim.treatment || 'Medical claim'}</strong><small>{claim.hospital_name || 'Unknown hospital'}</small></td>
                <td>₹{claim.amount ?? '—'}</td>
                <td>{claim.policy_decision || <span className="muted-text">Not verified</span>}</td>
                <td><span className={statusClass(claim.status)}>{claim.status || 'Pending'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filteredClaims.length ? <div className="empty-state"><div className="empty-state__icon">⌕</div><h3>No claims found</h3><p>Adjust the filters to see more claims.</p></div> : null}
      </div>
    </SectionCard>
  );
}
