import { useEffect, useMemo, useState } from 'react';

import { api } from '../../api';
import { Icon } from '../../components/Icon';
import { EmptyState, FlagList, PageHeader, Panel, StatusBadge, formatDate, formatMoney, statusInfo } from '../../components/ui';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'Waiting', match: (tone) => ['processing', 'waiting', 'review'].includes(tone) },
  { id: 'paid', label: 'Approved', match: (tone) => ['approved', 'partial'].includes(tone) },
  { id: 'rejected', label: 'Rejected', match: (tone) => tone === 'rejected' },
];

export function AdminClaimsPage() {
  const [claims, setClaims] = useState(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    api.get('/claims').then((response) => setClaims(response.data)).catch(() => setClaims([]));
  }, []);

  const visible = useMemo(() => {
    const test = FILTERS.find((item) => item.id === filter)?.match;
    const needle = query.trim().toLowerCase();
    return (claims || []).filter((claim) => {
      if (test && !test(statusInfo(claim.status).tone)) return false;
      return !needle || [claim.employee_name, claim.hospital_name, claim.treatment, claim.invoice_number, `#${claim.id}`]
        .join(' ').toLowerCase().includes(needle);
    });
  }, [claims, query, filter]);

  const total = visible.reduce((sum, claim) => sum + Number(claim.amount || 0), 0);

  return (
    <>
      <PageHeader title="All claims" description="Every claim submitted, with the policy check’s recommendation and the final status." />
      <Panel title={null}>
        <div className="toolbar">
          <div className="segmented" role="tablist" aria-label="Filter claims">
            {FILTERS.map((item) => (
              <button key={item.id} type="button" role="tab" aria-selected={filter === item.id}
                className={`segmented__option ${filter === item.id ? 'segmented__option--active' : ''}`}
                onClick={() => setFilter(item.id)}>{item.label}</button>
            ))}
          </div>
          <label className="search">
            <Icon name="search" size={16} />
            <input aria-label="Search all claims" placeholder="Search employee, hospital, treatment or invoice" value={query}
              onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>

        {claims === null ? <p className="loading-line">Loading claims…</p> : visible.length ? (
          <div className="table-wrap">
            <table className="claims-table">
              <thead>
                <tr><th>Claim</th><th>Employee</th><th>Treatment and hospital</th><th>Bill date</th>
                  <th className="num">Amount</th><th>Policy check</th><th>Status</th></tr>
              </thead>
              <tbody>
                {visible.map((claim) => (
                  <tr key={claim.id}>
                    <td className="cell-id">#{claim.id}</td>
                    <td><strong>{claim.employee_name}</strong></td>
                    <td>
                      <strong>{claim.treatment || 'Not read'}</strong>
                      <small>{claim.hospital_name || 'Hospital not read'}</small>
                      <FlagList flags={claim.risk_flags_json} />
                    </td>
                    <td className="cell-nowrap">{formatDate(claim.claim_date)}</td>
                    <td className="num">{formatMoney(claim.amount)}
                      {claim.final_approved_amount != null ? <small>{formatMoney(claim.final_approved_amount)} paid</small> : null}</td>
                    <td>{claim.policy_decision ? <>{claim.policy_decision}<small>{formatMoney(claim.policy_approved_amount)}</small></> : <span className="muted">Not checked</span>}</td>
                    <td><StatusBadge status={claim.status} /></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td colSpan={4}>{visible.length} {visible.length === 1 ? 'claim' : 'claims'}</td>
                  <td className="num">{formatMoney(total)}</td><td colSpan={2} /></tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <EmptyState icon="search" title={claims.length ? 'No claims match' : 'No claims yet'}>
            {claims.length ? 'Try a different search or filter.' : 'Claims appear here as employees submit bills.'}
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
