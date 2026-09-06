import { useRef, useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

const MAX_UPLOAD_SIZE_MB = 10;
const ACCEPTED_TYPES = '.png,.jpg,.jpeg,.webp,.pdf';

export function EmployeeUploadPage() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setResult(null);
    if (!file) { setError('Select a medical bill image or PDF first.'); return; }
    if (file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) { setError(`File size must not exceed ${MAX_UPLOAD_SIZE_MB} MB.`); return; }

    const formData = new FormData();
    formData.append('file', file);
    setSubmitting(true);
    try {
      const response = await api.post('/claims/upload', formData);
      setResult(response.data);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
    } catch (submissionError) {
      setError(submissionError.response?.data?.detail || 'Upload failed. Please try again.');
    } finally { setSubmitting(false); }
  };

  return (
    <div className="upload-layout">
      <SectionCard title="Submit a medical claim" subtitle="New claim">
        <form className="stack" onSubmit={onSubmit}>
          <div className="drop-zone" onClick={() => inputRef.current?.click()} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click(); }}>
            <div className="upload-icon">↑</div>
            <strong>{file ? file.name : 'Choose your medical bill'}</strong>
            <p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB selected` : 'Drag and drop or click to browse'}</p>
            <span>PDF, PNG, JPG or WebP · Max {MAX_UPLOAD_SIZE_MB} MB</span>
            <input ref={inputRef} type="file" accept={ACCEPTED_TYPES} onChange={(event) => setFile(event.target.files?.[0] || null)} disabled={submitting} />
          </div>
          <button type="submit" disabled={submitting || !file}>{submitting ? 'Processing claim…' : 'Upload & extract claim'}</button>
          {error ? <p className="error-text" role="alert">{error}</p> : null}
          {result ? (
            <div className="result-box result-box--success" role="status">
              <div className="result-heading"><div className="success-icon">✓</div><div><strong>Claim submitted</strong><p>We extracted the following information from your bill.</p></div></div>
              <div className="detail-grid">
                <div><span>Status</span><strong>{result.status}</strong></div>
                <div><span>Employee</span><strong>{result.employee_name}</strong></div>
                <div><span>Hospital</span><strong>{result.hospital_name || 'N/A'}</strong></div>
                <div><span>Treatment</span><strong>{result.treatment || 'N/A'}</strong></div>
                <div><span>Amount</span><strong>₹{result.amount ?? 'N/A'}</strong></div>
                <div><span>AI policy decision</span><strong>{result.policy_decision || 'Pending verification'}</strong></div>
              </div>
              <p className="muted-text">{result.validation_message || 'Your claim is now available in My Claims.'}</p>
            </div>
          ) : null}
        </form>
      </SectionCard>

      <aside className="card upload-help">
        <p className="eyebrow">Before you submit</p>
        <h2>For the best result</h2>
        <ul>
          <li>Use a clear, readable bill with all pages included.</li>
          <li>Make sure the hospital name and amount are visible.</li>
          <li>Our OCR extracts the bill details automatically.</li>
          <li>Policy evidence is checked before a decision is returned.</li>
        </ul>
      </aside>
    </div>
  );
}
