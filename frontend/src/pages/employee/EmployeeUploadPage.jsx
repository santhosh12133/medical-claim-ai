import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../../api';
import { ClaimOutcome, ExtractedFields } from '../../components/ClaimViews';
import { Icon } from '../../components/Icon';
import { PageHeader, Panel, errorMessage, isFinal } from '../../components/ui';

const MAX_UPLOAD_SIZE_MB = 10;
const ACCEPTED_TYPES = '.pdf,.png,.jpg,.jpeg,.webp';
const POLL_INTERVAL_MS = 2500;
const POLL_LIMIT = 72; // three minutes

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
        const read = ['completed', 'failed'].includes(response.data.processing_status);
        // Once the bill is read, give the policy check a moment to attach its result.
        if ((read && (response.data.policy_decision || isFinal(response.data.status) || attempts > 6)) || attempts >= POLL_LIMIT) {
          setPolling(false);
        }
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
      setError(`This file is larger than ${MAX_UPLOAD_SIZE_MB} MB. Upload a smaller scan or photo.`);
      return;
    }
    setFile(selected);
  };

  const reset = () => {
    setClaim(null);
    setFile(null);
    setTreatment('');
    setDeclaredAmount('');
    if (inputRef.current) inputRef.current.value = '';
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    if (!file) { setError('Choose the bill to upload first.'); return; }
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
      if (inputRef.current) inputRef.current.value = '';
    } catch (submissionError) {
      setError(errorMessage(submissionError, 'The bill could not be uploaded. Try again.'));
    } finally {
      setSubmitting(false);
    }
  };

  const reading = claim && ['queued', 'processing'].includes(claim.processing_status);

  return (
    <>
      <PageHeader title="Submit a bill" description="Upload one hospital or pharmacy bill per claim. It’s checked against your reimbursement policy as soon as it arrives." />

      <div className="split split--form">
        {claim ? (
          <Panel className="result-box" title={null}>
            <div className="result-heading" role="status" aria-live="polite">
              <span className={`result-heading__icon ${reading ? 'result-heading__icon--busy' : ''}`}>
                {reading ? <span className="spinner" aria-hidden="true" /> : <Icon name="check" size={18} />}
              </span>
              <div>
                <strong>{reading ? `Claim #${claim.id} is being processed` : `Claim #${claim.id} processed`}</strong>
                <p>{reading ? 'Reading the bill and checking it against your policy…' : 'Here is what was read from your bill and the result.'}</p>
              </div>
            </div>
            {reading ? <div className="progress" aria-hidden="true"><div className="progress__bar" /></div> : <ClaimOutcome claim={claim} />}
            <ExtractedFields claim={claim} reading={reading} />
            <div className="button-row">
              <Link className="button button--secondary" to="/employee/claims">Go to my claims</Link>
              <button type="button" className="button button--ghost" onClick={reset}>Submit another bill</button>
            </div>
          </Panel>
        ) : (
          <Panel title={null}>
            <form className="form" onSubmit={onSubmit}>
              <div
                className={`drop-zone ${dragging ? 'drop-zone--active' : ''} ${file ? 'drop-zone--chosen' : ''}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files?.[0]); }}
                role="button"
                tabIndex={0}
                aria-label="Choose the bill to upload"
                onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inputRef.current?.click(); } }}
              >
                <span className="drop-zone__icon"><Icon name={file ? 'file' : 'submit'} size={24} /></span>
                <strong>{file ? file.name : 'Drop the bill here, or choose a file'}</strong>
                <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB, ready to submit` : `PDF, JPG, PNG or WebP, up to ${MAX_UPLOAD_SIZE_MB} MB`}</span>
                <input ref={inputRef} type="file" accept={ACCEPTED_TYPES} onChange={(event) => chooseFile(event.target.files?.[0] || null)} disabled={submitting} />
              </div>

              <div className="form-row">
                <label className="field">
                  <span className="field__label">Treatment <span className="field__optional">optional</span></span>
                  <input value={treatment} maxLength={120} placeholder="For example, root canal or MRI scan" onChange={(event) => setTreatment(event.target.value)} />
                  <span className="field__hint">Helps when the bill doesn’t name the treatment clearly.</span>
                </label>
                <label className="field">
                  <span className="field__label">Amount you’re claiming <span className="field__optional">optional</span></span>
                  <input type="number" inputMode="decimal" min="1" step="0.01" value={declaredAmount} placeholder="₹"
                    onChange={(event) => setDeclaredAmount(event.target.value)} />
                  <span className="field__hint">Checked against the total on the bill.</span>
                </label>
              </div>

              {error ? <p className="form-error" role="alert"><Icon name="alert" size={16} />{error}</p> : null}
              <div className="button-row">
                <button type="submit" className="button button--primary" disabled={submitting || !file}>
                  {submitting ? 'Submitting…' : 'Submit claim'}
                </button>
              </div>
            </form>
          </Panel>
        )}

        <Panel title="Before you submit" className="panel--quiet">
          <ul className="checklist">
            <li><Icon name="check" size={16} />The hospital name, bill date and total are readable.</li>
            <li><Icon name="check" size={16} />The bill is in the patient’s name on your account.</li>
            <li><Icon name="check" size={16} />Every page of a multi-page bill is in one file.</li>
            <li><Icon name="check" size={16} />Each bill is submitted once. Repeat uploads are detected.</li>
          </ul>
          <p className="panel__footnote">Not sure it’s covered? <Link to="/employee/assistant">Ask a coverage question</Link> first.</p>
        </Panel>
      </div>
    </>
  );
}
