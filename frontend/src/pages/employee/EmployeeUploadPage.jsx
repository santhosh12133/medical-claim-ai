import { useState } from 'react';

import { api } from '../../api';
import { SectionCard } from '../../components/SectionCard';

export function EmployeeUploadPage() {
  const [employeeName, setEmployeeName] = useState('Santhosh');
  const [treatment, setTreatment] = useState('Dental');
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setResult(null);

    if (!file) {
      setError('Select a medical bill image first.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('employee_name', employeeName);
    formData.append('treatment', treatment);

    try {
      const response = await api.post('/claims/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (submissionError) {
      setError(submissionError.response?.data?.detail || 'Upload failed');
    }
  };

  return (
    <SectionCard title="Upload Medical Bill" subtitle="Employee side">
      <form className="stack" onSubmit={onSubmit}>
        <label>
          Employee name
          <input value={employeeName} onChange={(event) => setEmployeeName(event.target.value)} />
        </label>
        <label>
          Treatment
          <input value={treatment} onChange={(event) => setTreatment(event.target.value)} />
        </label>
        <label>
          Bill image
          <input type="file" accept="image/*" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </label>
        <button type="submit">Upload and Extract</button>
        {error ? <p className="error-text">{error}</p> : null}
        {result ? (
          <div className="result-box">
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
