import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';
import { errorMessage, statusClass } from '../../components/ui';

const EMPTY_FORM = {
  title: '',
  policy_type: '',
  policy_version: '1.0',
  department: 'Medical',
  effective_from: '',
  effective_to: '',
  supersede_previous: true,
};

function PolicyUpload({ categories, onUploaded }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [message, setMessage] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!file) {
      setMessage({ type: 'error', text: 'Choose a policy PDF first.' });
      return;
    }
    const data = new FormData();
    data.append('file', file);
    Object.entries(form).forEach(([key, value]) => {
      if (value !== '' && value !== null) data.append(key, String(value));
    });
    setSubmitting(true);
    setMessage(null);
    try {
      const response = await api.post('/rag/policies/ingest', data);
      const superseded = response.data.superseded_document_ids?.length
        ? ` Archived previous version(s): #${response.data.superseded_document_ids.join(', #')}.`
        : '';
      setMessage({ type: 'success', text: `Indexed “${response.data.title}” into ${response.data.chunk_count} chunks.${superseded}` });
      setFile(null);
      setForm(EMPTY_FORM);
      if (inputRef.current) inputRef.current.value = '';
      onUploaded();
    } catch (uploadError) {
      setMessage({ type: 'error', text: errorMessage(uploadError, 'Policy upload failed.') });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="policy-form" onSubmit={submit}>
      <label className="policy-form__file">
        Policy PDF
        <input ref={inputRef} type="file" accept=".pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </label>
      <label>Title<input required minLength={3} value={form.title} onChange={update('title')} placeholder="Dental Care Reimbursement Policy" /></label>
      <label>
        Policy type
        <input required list="policy-categories" value={form.policy_type} onChange={update('policy_type')} placeholder="Dental" />
        <datalist id="policy-categories">{categories.map((name) => <option key={name} value={name} />)}</datalist>
      </label>
      <label>Version<input required value={form.policy_version} onChange={update('policy_version')} /></label>
      <label>Department<input required value={form.department} onChange={update('department')} /></label>
      <label>Effective from<input type="date" value={form.effective_from} onChange={update('effective_from')} /></label>
      <label>Effective to<input type="date" value={form.effective_to} onChange={update('effective_to')} /></label>
      <label className="checkbox">
        <input type="checkbox" checked={form.supersede_previous} onChange={update('supersede_previous')} />
        Archive older active versions of this policy type
      </label>
      <button type="submit" disabled={submitting}>{submitting ? 'Parsing, chunking & embedding…' : 'Upload & index policy'}</button>
      {message ? <p className={message.type === 'error' ? 'error-text' : 'success-text'} role="status">{message.text}</p> : null}
    </form>
  );
}

function RetrievalDebugger() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const search = async (event) => {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setError('');
    try {
      const response = await api.post('/rag/search', { query: query.trim(), top_k: 8 });
      setResult(response.data);
    } catch (searchError) {
      setError(errorMessage(searchError, 'Search failed.'));
    }
  };

  return (
    <div className="stack">
      <form className="toolbar toolbar--search" onSubmit={search}>
        <input aria-label="Retrieval test query" placeholder="Try “root canal limit” or “MRI 30000”" value={query} onChange={(event) => setQuery(event.target.value)} />
        <button type="submit">Search</button>
      </form>
      {error ? <p className="error-text">{error}</p> : null}
      {result ? (
        <>
          <p className="muted-text">
            {result.diagnostics.mode} search · category {result.diagnostics.category || '—'} · {result.diagnostics.vector_candidates} vector /
            {' '}{result.diagnostics.lexical_candidates} BM25 candidates · {result.diagnostics.latency_ms} ms
          </p>
          <div className="table-wrap">
            <table className="claims-table">
              <thead><tr><th>#</th><th>Policy</th><th>Relevance</th><th>Vector</th><th>BM25</th><th>RRF</th><th>Rerank</th><th>Text</th></tr></thead>
              <tbody>
                {result.hits.map((hit, index) => (
                  <tr key={hit.chunk_id}>
                    <td>{index + 1}</td>
                    <td><strong>{hit.title}</strong><small>{hit.policy_type} v{hit.policy_version}{hit.page_start ? ` · p.${hit.page_start}` : ''}</small></td>
                    <td>{Math.round(hit.similarity * 100)}%</td>
                    <td>{hit.vector_score != null ? hit.vector_score.toFixed(3) : '—'}</td>
                    <td>{hit.lexical_score != null ? hit.lexical_score.toFixed(2) : '—'}</td>
                    <td>{hit.fused_score != null ? hit.fused_score.toFixed(4) : '—'}</td>
                    <td>{hit.rerank_score != null ? hit.rerank_score.toFixed(3) : '—'}</td>
                    <td className="cell-text">{hit.chunk_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function AdminPoliciesPage() {
  const [policies, setPolicies] = useState([]);
  const [categories, setCategories] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    const response = await api.get('/rag/policies', { params: statusFilter ? { status_filter: statusFilter } : {} });
    setPolicies(response.data);
  }, [statusFilter]);

  useEffect(() => {
    load().catch(() => setPolicies([]));
  }, [load]);

  useEffect(() => {
    api.get('/rag/taxonomy')
      .then((response) => setCategories(response.data.categories.map((item) => item.category)))
      .catch(() => setCategories([]));
  }, []);

  const act = async (policy, label, request) => {
    setBusyId(policy.id);
    setNotice('');
    try {
      await request();
      setNotice(`${label}: ${policy.title}`);
      await load();
    } catch (actionError) {
      setNotice(errorMessage(actionError, `${label} failed`));
    } finally {
      setBusyId(null);
    }
  };

  const setStatus = (policy, status) => {
    const data = new FormData();
    data.append('new_status', status);
    return act(policy, `Marked ${status}`, () => api.patch(`/rag/policies/${policy.id}/status`, data));
  };

  const remove = (policy) => {
    if (!window.confirm(`Delete “${policy.title}” and its ${policy.chunk_count} indexed chunks? This cannot be undone.`)) return undefined;
    return act(policy, 'Deleted', () => api.delete(`/rag/policies/${policy.id}`));
  };

  return (
    <>
      <SectionCard title="Upload a policy" subtitle="Knowledge base">
        <PolicyUpload categories={categories} onUploaded={() => load().catch(() => undefined)} />
      </SectionCard>

      <SectionCard title="Indexed policies" subtitle={`${policies.length} documents`}>
        <div className="toolbar toolbar--compact">
          <select aria-label="Filter policies by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="archived">Archived</option>
          </select>
          {notice ? <span className="muted-text">{notice}</span> : null}
        </div>
        <div className="table-wrap">
          <table className="claims-table">
            <thead><tr><th>Policy</th><th>Type</th><th>Effective</th><th>Chunks</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {policies.map((policy) => (
                <tr key={policy.id}>
                  <td><strong>{policy.title}</strong><small>#{policy.id} · v{policy.policy_version} · {policy.source_filename}</small></td>
                  <td>{policy.policy_type}<small>{policy.department}</small></td>
                  <td>{policy.effective_from || '—'}<small>to {policy.effective_to || 'open'}</small></td>
                  <td>{policy.chunk_count}</td>
                  <td><span className={statusClass(policy.status)}>{policy.status}</span></td>
                  <td>
                    <div className="button-row button-row--tight">
                      {policy.status !== 'active'
                        ? <button type="button" className="secondary" disabled={busyId === policy.id} onClick={() => setStatus(policy, 'active')}>Activate</button>
                        : <button type="button" className="secondary" disabled={busyId === policy.id} onClick={() => setStatus(policy, 'archived')}>Archive</button>}
                      <button type="button" className="secondary" disabled={busyId === policy.id} onClick={() => act(policy, 'Re-indexed', () => api.post(`/rag/policies/${policy.id}/reindex`))}>Re-index</button>
                      <button type="button" className="secondary danger" disabled={busyId === policy.id} onClick={() => remove(policy)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!policies.length ? <div className="empty-state"><div className="empty-state__icon">§</div><h3>No policies yet</h3><p>Upload a policy PDF or run the demo seed script.</p></div> : null}
        </div>
      </SectionCard>

      <SectionCard title="Retrieval debugger" subtitle="Inspect hybrid search scores">
        <RetrievalDebugger />
      </SectionCard>
    </>
  );
}
