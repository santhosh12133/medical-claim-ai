import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../../api';
import { Icon } from '../../components/Icon';
import { EmptyState, PageHeader, Panel, StatusBadge, Toast, errorMessage, formatDate } from '../../components/ui';

const EMPTY_FORM = {
  title: '', policy_type: '', policy_version: '1.0', department: 'Medical', effective_from: '', effective_to: '', supersede_previous: true,
};

function PolicyUpload({ categories, onUploaded, notify }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const update = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    if (!file) { setError('Choose the policy PDF first.'); return; }
    const data = new FormData();
    data.append('file', file);
    Object.entries(form).forEach(([key, value]) => { if (value !== '' && value !== null) data.append(key, String(value)); });
    setSubmitting(true);
    try {
      const response = await api.post('/rag/policies/ingest', data);
      const archived = response.data.superseded_document_ids?.length
        ? ` Older version${response.data.superseded_document_ids.length > 1 ? 's' : ''} archived.` : '';
      notify('success', `“${response.data.title}” added`, `Split into ${response.data.chunk_count} searchable passages.${archived}`);
      setFile(null);
      setForm(EMPTY_FORM);
      if (inputRef.current) inputRef.current.value = '';
      onUploaded();
    } catch (uploadError) {
      setError(errorMessage(uploadError, 'The policy could not be added.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="form" onSubmit={submit}>
      <label className="field">
        <span className="field__label">Policy PDF</span>
        <input ref={inputRef} type="file" accept=".pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </label>
      <div className="form-row">
        <label className="field"><span className="field__label">Title</span>
          <input required minLength={3} value={form.title} onChange={update('title')} placeholder="Dental Care Reimbursement Policy" /></label>
        <label className="field"><span className="field__label">Category</span>
          <input required list="policy-categories" value={form.policy_type} onChange={update('policy_type')} placeholder="Dental" />
          <datalist id="policy-categories">{categories.map((name) => <option key={name} value={name} />)}</datalist></label>
      </div>
      <div className="form-row form-row--4">
        <label className="field"><span className="field__label">Version</span><input required value={form.policy_version} onChange={update('policy_version')} /></label>
        <label className="field"><span className="field__label">Department</span><input required value={form.department} onChange={update('department')} /></label>
        <label className="field"><span className="field__label">In force from</span><input type="date" value={form.effective_from} onChange={update('effective_from')} /></label>
        <label className="field"><span className="field__label">Until</span><input type="date" value={form.effective_to} onChange={update('effective_to')} /></label>
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={form.supersede_previous} onChange={update('supersede_previous')} />
        Archive older active versions in this category
      </label>
      {error ? <p className="form-error" role="alert"><Icon name="alert" size={16} />{error}</p> : null}
      <div className="button-row">
        <button type="submit" className="button button--primary" disabled={submitting}>{submitting ? 'Reading the policy…' : 'Add policy'}</button>
      </div>
    </form>
  );
}

function SearchTest() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const search = async (event) => {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setError('');
    setLoading(true);
    try {
      const response = await api.post('/rag/search', { query: query.trim(), top_k: 8 });
      setResult(response.data);
    } catch (searchError) {
      setError(errorMessage(searchError, 'The search didn’t work. Try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-test">
      <form className="toolbar" onSubmit={search}>
        <label className="search search--wide">
          <Icon name="search" size={16} />
          <input aria-label="Retrieval test query" placeholder="For example, root canal limit or MRI 30000" value={query}
            onChange={(event) => setQuery(event.target.value)} />
        </label>
        <button type="submit" className="button button--secondary" disabled={loading}>Search</button>
      </form>
      {error ? <p className="form-error" role="alert"><Icon name="alert" size={16} />{error}</p> : null}
      {result ? (
        <>
          <p className="search-test__summary">
            {result.hits.length} passages found in {result.diagnostics.latency_ms} ms
            {result.diagnostics.category ? `, matched to the ${result.diagnostics.category} category` : ''}.
          </p>
          <ol className="citation-list">
            {result.hits.map((hit, index) => (
              <li key={hit.chunk_id} className="citation">
                <div className="citation__head">
                  <span className="citation__id">{index + 1}</span>
                  <strong>{hit.title}</strong>
                  <span className="citation__where">Version {hit.policy_version}{hit.page_start ? `, page ${hit.page_start}` : ''}</span>
                  <span className="citation__score">{Math.round(hit.similarity * 100)}% match</span>
                </div>
                <p>{hit.chunk_text}</p>
                <details className="score-details">
                  <summary>Scores</summary>
                  <dl>
                    <div><dt>Meaning (vector)</dt><dd>{hit.vector_score != null ? hit.vector_score.toFixed(3) : '—'}</dd></div>
                    <div><dt>Keywords (BM25)</dt><dd>{hit.lexical_score != null ? hit.lexical_score.toFixed(2) : '—'}</dd></div>
                    <div><dt>Combined (RRF)</dt><dd>{hit.fused_score != null ? hit.fused_score.toFixed(4) : '—'}</dd></div>
                    <div><dt>Re-ranked</dt><dd>{hit.rerank_score != null ? hit.rerank_score.toFixed(3) : '—'}</dd></div>
                  </dl>
                </details>
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </div>
  );
}

export function AdminPoliciesPage() {
  const [policies, setPolicies] = useState(null);
  const [categories, setCategories] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [toast, setToast] = useState(null);
  const [confirmId, setConfirmId] = useState(null);

  const notify = (type, title, message) => setToast({ type, title, message });
  const closeToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    const response = await api.get('/rag/policies', { params: statusFilter ? { status_filter: statusFilter } : {} });
    setPolicies(response.data);
  }, [statusFilter]);

  useEffect(() => { load().catch(() => setPolicies([])); }, [load]);
  useEffect(() => {
    api.get('/rag/taxonomy').then((response) => setCategories(response.data.categories.map((item) => item.category))).catch(() => setCategories([]));
  }, []);

  const act = async (policy, done, request) => {
    setBusyId(policy.id);
    try {
      await request();
      notify('success', done, policy.title);
      await load();
    } catch (actionError) {
      notify('error', 'That didn’t work', errorMessage(actionError));
    } finally {
      setBusyId(null);
      setConfirmId(null);
    }
  };

  const setStatus = (policy, status) => {
    const data = new FormData();
    data.append('new_status', status);
    return act(policy, status === 'active' ? 'Policy activated' : 'Policy archived', () => api.patch(`/rag/policies/${policy.id}/status`, data));
  };

  const list = policies || [];
  const active = list.filter((policy) => policy.status === 'active').length;

  return (
    <>
      <PageHeader title="Policies"
        description="The reimbursement policies every claim is checked against. Only active policies are used." />
      <Toast toast={toast} onClose={closeToast} />

      <Panel title="Policy library" description={policies ? `${active} active of ${list.length}` : null}
        actions={(
          <select className="select" aria-label="Filter policies by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All statuses</option><option value="active">Active</option>
            <option value="inactive">Inactive</option><option value="archived">Archived</option>
          </select>
        )}>
        {policies === null ? <p className="loading-line">Loading policies…</p> : list.length ? (
          <div className="table-wrap">
            <table className="claims-table">
              <thead><tr><th>Policy</th><th>Category</th><th>In force</th><th className="num">Passages</th><th>Status</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {list.map((policy) => (
                  <tr key={policy.id}>
                    <td><strong>{policy.title}</strong><small>Version {policy.policy_version}, {policy.source_filename}</small></td>
                    <td>{policy.policy_type}<small>{policy.department}</small></td>
                    <td className="cell-nowrap">{policy.effective_from ? formatDate(policy.effective_from) : 'Always'}
                      <small>{policy.effective_to ? `until ${formatDate(policy.effective_to)}` : 'no end date'}</small></td>
                    <td className="num">{policy.chunk_count}</td>
                    <td><StatusBadge status={policy.status} /></td>
                    <td>
                      <div className="row-actions">
                        {confirmId === policy.id ? (
                          <>
                            <span className="row-actions__ask">Delete for good?</span>
                            <button type="button" className="button button--danger button--small" disabled={busyId === policy.id}
                              onClick={() => act(policy, 'Policy deleted', () => api.delete(`/rag/policies/${policy.id}`))}>Delete</button>
                            <button type="button" className="button button--ghost button--small" onClick={() => setConfirmId(null)}>Keep</button>
                          </>
                        ) : (
                          <>
                            {policy.status !== 'active'
                              ? <button type="button" className="button button--ghost button--small" disabled={busyId === policy.id} onClick={() => setStatus(policy, 'active')}>Activate</button>
                              : <button type="button" className="button button--ghost button--small" disabled={busyId === policy.id} onClick={() => setStatus(policy, 'archived')}>Archive</button>}
                            <button type="button" className="button button--ghost button--small" disabled={busyId === policy.id}
                              onClick={() => act(policy, 'Policy re-read', () => api.post(`/rag/policies/${policy.id}/reindex`))}>Re-read</button>
                            <button type="button" className="button button--ghost button--small button--danger-text" disabled={busyId === policy.id}
                              onClick={() => setConfirmId(policy.id)}>Delete</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState icon="policies" title="No policies">Add a policy PDF below. Claims can’t be checked until one is active.</EmptyState>}
      </Panel>

      <div className="split split--even">
        <Panel title="Add a policy" description="Upload a policy PDF. It’s read, split into passages and made searchable.">
          <PolicyUpload categories={categories} onUploaded={() => load().catch(() => undefined)} notify={notify} />
        </Panel>
        <Panel title="Test a search" description="See which policy passages a claim or question would match.">
          <SearchTest />
        </Panel>
      </div>
    </>
  );
}
