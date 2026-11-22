import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';
import { FlagList, errorMessage, formatMoney, statusClass } from '../../components/ui';

const MAX_UPLOAD_SIZE_MB = 10;
const ACCEPTED_TYPES = '.png,.jpg,.jpeg,.webp,.pdf';
const POLL_INTERVAL_MS = 2500;
const POLL_LIMIT = 48; // ~2 minutes

export function EmployeeUploadPage() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [treatment, setTreatment] = useState('');
  const [declaredAmount, setDeclaredAmount] = useState('');
  const [dragging, setDragging] = useState(false);
  const [claim, setClaim] = useState(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!claim || !polling) return undefined;
    let attempts = 0;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      attempts += 1;
      try {
        const response = await api.get(`/claims/${claim.id}`);
        if (cancelled) return;
        setClaim(response.data);
        const done = ['completed', 'failed'].includes(response.data.processing_status);
        // After OCR completes, give policy verification a moment to attach its recommendation.
        if ((done && (response.data.policy_decision || attempts > 6)) || attempts >= POLL_LIMIT) setPolling(false);
      } catch {
        setPolling(false);
      }
    }, POLL_INTERVAL_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [claim?.id, polling]);

  const chooseFile = (selected) => {
    setError('');
    if (!selected) return;
    if (selected.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
      setError(`File size must not exceed ${MAX_UPLOAD_SIZE_MB} MB.`);
      return;
    }
    setFile(selected);
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setClaim(null);
    if (!file) { setError('Select a medical bill image or PDF first.'); return; }

    const formData = new FormData();
    formData.append('file', file);
    if (treatment.trim()) formData.append('treatment', treatment.trim());
    if (declaredAmount) formData.append('declared_amount', declaredAmount);
    setSubmitting(true);
    try {
      const response = await api.post('/claims/upload', formData);
      setClaim(response.data);
      setPolling(true);
      setFile(null);
      setTreatment('');
      setDeclaredAmount('');
      if (inputRef.current) inputRef.current.value = '';
    } catch (submissionError) {
      setError(errorMessage(submissionError, 'Upload failed. Please try again.'));
    } finally { setSubmitting(false); }
  };

  const processing = claim && ['queued', 'processing'].includes(claim.processing_status);

  return (
    <div className="upload-layout">
      <SectionCard title="Submit a medical claim" subtitle="New claim">
        <form className="stack" onSubmit={onSubmit}>
          <div
            className={`drop-zone ${dragging ? 'drop-zone--active' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files?.[0]); }}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click(); }}
          >
            <div className="upload-icon">↑</div>
            <strong>{file ? file.name : 'Choose your medical bill'}</strong>
            <p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB selected` : 'Drag and drop or click to browse'}</p>
            <span>PDF, PNG, JPG or WebP · Max {MAX_UPLOAD_SIZE_MB} MB</span>
            <input ref={inputRef} type="file" accept={ACCEPTED_TYPES} onChange={(event) => chooseFile(event.target.files?.[0] || null)} disabled={submitting} />
          </div>
          <label>
            Treatment (optional)
            <input value={treatment} maxLength={120} placeholder="e.g. Root canal, MRI scan, Physiotherapy" onChange={(event) => setTreatment(event.target.value)} />
          </label>
          <label>
            Amount you are claiming (optional)
            <input type="number" min="1" step="0.01" value={declaredAmount} placeholder="₹ — checked against the bill total"
              onChange={(event) => setDeclaredAmount(event.target.value)} />
          </label>
          <button type="submit" disabled={submitting || !file}>{submitting ? 'Uploading…' : 'Upload & submit claim'}</button>
          {error ? <p className="error-text" role="alert">{error}</p> : null}

          {claim ? (
            <div className="result-box result-box--success" role="status" aria-live="polite">
              <div className="result-heading">
                <div className="success-icon">{processing ? '…' : '✓'}</div>
                <div>
                  <strong>{processing ? `Claim #${claim.id} is being processed` : `Claim #${claim.id} processed`}</strong>
                  <p>{processing ? 'Reading your bill and checking it against policy…' : 'Here is what we extracted and the policy check result.'}</p>
                </div>
              </div>
              {processing ? <div className="progress"><div className="progress__bar" /></div> : null}
              <div className="detail-grid">
                <div><span>Status</span><strong><span className={statusClass(claim.status)}>{claim.status}</span></strong></div>
                <div><span>Treatment</span><strong>{claim.treatment || (processing ? 'Reading…' : 'Not found')}</strong></div>
                <div><span>Hospital</span><strong>{claim.hospital_name || (processing ? 'Reading…' : 'Not found')}</strong></div>
                <div><span>Bill amount</span><strong>{claim.amount != null ? formatMoney(claim.amount) : (processing ? 'Reading…' : 'Not found')}</strong></div>
                <div><span>Bill date</span><strong>{claim.claim_date || (processing ? 'Reading…' : 'Not found')}</strong></div>
                <div><span>Policy check</span><strong>{claim.policy_decision ? `${claim.policy_decision} · ${formatMoney(claim.policy_approved_amount)}` : 'Pending'}</strong></div>
              </div>
              <FlagList flags={claim.risk_flags_json} />
              <p className="muted-text">{claim.policy_reason || claim.validation_message}</p>
              <Link className="primary-link" to="/employee/status">Track in Claim Status</Link>
            </div>
          ) : null}
        </form>
      </SectionCard>

      <aside className="card upload-help">
        <p className="eyebrow">Before you submit</p>
        <h2>For the best result</h2>
        <ul>
          <li>Use a clear, readable bill with all pages included.</li>
          <li>Make sure the hospital name, date and total amount are visible.</li>
          <li>Adding the treatment helps match the right policy faster.</li>
          <li>Each bill can be submitted once; duplicates are detected automatically.</li>
          <li>Not sure what is covered? Ask the <Link to="/employee/assistant">Coverage Assistant</Link>.</li>
        </ul>
      </aside>
    </div>
  );
}
