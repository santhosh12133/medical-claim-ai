import { useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

const MAX_UPLOAD_SIZE_MB = 10;
const ACCEPTED_TYPES = '.png,.jpg,.jpeg,.webp,.pdf';

export function EmployeeUploadPage() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setResult(null);

    if (!file) {
      setError('Select a medical bill image or PDF first.');
      return;
    }

    if (file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
      setError(`File size must not exceed ${MAX_UPLOAD_SIZE_MB} MB.`);
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setSubmitting(true);
    try {
      const response = await api.post('/claims/upload', formData);
      setResult(response.data);
      setFile(null);
      event.target.reset();
    } catch (submissionError) {
      setError(submissionError.response?.data?.detail || 'Upload failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SectionCard title="Upload Medical Bill" subtitle="Upload a bill and let the system extract claim details automatically.">
      <form className="stack" onSubmit={onSubmit}>
        <label>
          Medical bill
          <input
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            disabled={submitting}
          />
        </label>
        <p className="muted-text">Supported: PNG, JPG, JPEG, WebP and PDF · Maximum {MAX_UPLOAD_SIZE_MB} MB</p>
        {file ? <p className="muted-text">Selected: {file.name}</p> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Processing…' : 'Upload and Extract'}
        </button>
        {error ? <p className="error-text" role="alert">{error}</p> : null}
        {result ? (
          <div className="result-box" role="status">
            <p><strong>Status:</strong> {result.status}</p>
            <p><strong>Employee:</strong> {result.employee_name}</p>
            <p><strong>Hospital:</strong> {result.hospital_name || 'N/A'}</p>
            <p><strong>Treatment:</strong> {result.treatment || 'N/A'}</p>
            <p><strong>Amount:</strong> {result.amount ?? 'N/A'}</p>
            <p><strong>Policy decision:</strong> {result.policy_decision || 'Not verified yet'}</p>
            <p><strong>Validation:</strong> {result.validation_message || 'N/A'}</p>
          </div>
        ) : null}
      </form>
    </SectionCard>
  );
}
