import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

const statusClass = (status) => `status-pill status-${String(status || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

export function EmployeeClaimsPage() {
  const [claims, setClaims] = useState([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All');

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const filteredClaims = useMemo(() => claims.filter((claim) => {
    const haystack = [claim.hospital_name, claim.treatment, claim.employee_name, claim.policy_decision].join(' ').toLowerCase();
    return haystack.includes(query.toLowerCase()) && (status === 'All' || claim.status === status);
  }), [claims, query, status]);

  const statuses = ['All', ...new Set(claims.map((claim) => claim.status).filter(Boolean))];

  return (
    <SectionCard title="My Claims" subtitle="Claim history and search">
      <div className="toolbar">
        <input aria-label="Search claims" placeholder="Search hospital, treatment or policy..." value={query} onChange={(event) => setQuery(event.target.value)} />
        <select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}>
          {statuses.map((item) => <option key={item}>{item}</option>)}
        </select>
        <Link className="primary-link" to="/employee/upload">+ New Claim</Link>
      </div>
      <div className="list-grid">
        {filteredClaims.length ? filteredClaims.map((claim) => (
          <article key={claim.id} className="claim-card">
            <div className="claim-card__main">
              <div className="claim-card__title">
                <div className="claim-icon">₹</div>
                <div><h3>{claim.treatment || 'Medical claim'}</h3><p>{claim.hospital_name || 'Unknown hospital'}</p></div>
              </div>
              <div className="claim-meta"><span>Claim #{claim.id}</span><span>Amount: ₹{claim.amount ?? '—'}</span><span>Policy: {claim.policy_decision || 'Pending'}</span></div>
            </div>
            <span className={statusClass(claim.status)}>{claim.status || 'Pending'}</span>
          </article>
        )) : <div className="empty-state"><div className="empty-state__icon">⌕</div><h3>No matching claims</h3><p>Try another search or submit a new medical bill.</p><Link className="primary-link" to="/employee/upload">Submit a claim</Link></div>}
      </div>
    </SectionCard>
  );
}
