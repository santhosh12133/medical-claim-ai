import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { ClaimOutcome, ClaimRow, ClaimTimeline, ExtractedFields } from '../../components/ClaimViews';
import { Icon } from '../../components/Icon';
import { EmptyState, PageHeader, Panel, statusInfo } from '../../components/ui';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'In progress', match: (tone) => ['processing', 'waiting', 'review'].includes(tone) },
  { id: 'paid', label: 'Approved', match: (tone) => ['approved', 'partial'].includes(tone) },
  { id: 'rejected', label: 'Rejected', match: (tone) => tone === 'rejected' },
];

export function EmployeeClaimsPage() {
  const [claims, setClaims] = useState(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    api.get('/claims')
      .then((response) => {
        setClaims(response.data);
        if (response.data.length) setOpenId(response.data[0].id);
      })
      .catch(() => setClaims([]));
  }, []);

  const visible = useMemo(() => {
    const test = FILTERS.find((item) => item.id === filter)?.match;
    const needle = query.trim().toLowerCase();
    return (claims || []).filter((claim) => {
      if (test && !test(statusInfo(claim.status).tone)) return false;
      if (!needle) return true;
      return [claim.treatment, claim.hospital_name, claim.invoice_number, `#${claim.id}`].join(' ').toLowerCase().includes(needle);
    });
  }, [claims, query, filter]);

  return (
    <>
      <PageHeader
        title="My claims"
        description="Every bill you’ve submitted, where it stands, and the reason for each decision."
        actions={<Link className="button button--primary" to="/employee/upload"><Icon name="submit" />Submit a bill</Link>}
      />

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
            <input aria-label="Search claims" placeholder="Search treatment, hospital or invoice" value={query}
              onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>

        {claims === null ? <p className="loading-line">Loading claims…</p> : visible.length ? (
          <div className="claim-list">
            <div className="claim-list__head" aria-hidden="true">
              <span>Claim</span><span>Bill date</span><span>Amount</span><span>Status</span>
            </div>
            {visible.map((claim) => (
              <div key={claim.id} className="claim-item">
                <ClaimRow claim={claim} expanded={openId === claim.id}
                  onToggle={() => setOpenId(openId === claim.id ? null : claim.id)} />
                {openId === claim.id ? (
                  <div className="claim-item__detail">
                    <ClaimTimeline claim={claim} />
                    <ClaimOutcome claim={claim} />
                    <ExtractedFields claim={claim} />
                    <p className="claim-item__ref">Claim #{claim.id}</p>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : claims.length ? (
          <EmptyState icon="search" title="No claims match">Try a different search or filter.</EmptyState>
        ) : (
          <EmptyState title="No claims yet" action={<Link className="button button--primary" to="/employee/upload">Submit your first bill</Link>}>
            Bills you submit appear here with their progress and decision.
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
