export const statusClass = (status) => `status-pill status-${String(status || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

export function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return `₹${number.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function formatPercent(value) {
  if (value === null || value === undefined) return '—';
  return `${(Number(value) * 100).toFixed(0)}%`;
}

export function errorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(', ');
  return fallback;
}

const FLAG_LABELS = {
  DUPLICATE_DOCUMENT: 'Duplicate document',
  DUPLICATE_INVOICE: 'Duplicate invoice',
  FUTURE_DATED_BILL: 'Future-dated bill',
  STALE_BILL: 'Old bill',
  PATIENT_NAME_MISMATCH: 'Patient name differs',
  OCR_LOW_QUALITY: 'Low OCR quality',
  OCR_FIELD_DISAGREEMENT: 'OCR passes disagree',
  CONFLICTING_POLICY_LIMITS: 'Conflicting policy limits',
  PREAUTHORIZATION_REQUIRED: 'Pre-authorisation required',
  LATE_SUBMISSION: 'Late submission',
  PER_DAY_LIMIT: 'Per-day limit',
  PARTIAL_APPROVAL: 'Partial approval',
  LIMIT_EXHAUSTED: 'Limit exhausted',
  ANNUAL_LIMIT_APPLIED: 'Annual limit applied',
  EXCLUSION_MATCHED: 'Policy exclusion',
  COPAY_APPLIED: 'Co-pay applied',
  NO_POLICY_FOUND: 'No policy found',
  LIMIT_NOT_FOUND: 'Limit not found',
  LOW_CONFIDENCE: 'Low confidence',
  PROMPT_INJECTION_SUSPECTED: 'Suspicious document text',
};

const BLOCKING = new Set([
  'DUPLICATE_DOCUMENT', 'DUPLICATE_INVOICE', 'FUTURE_DATED_BILL', 'PATIENT_NAME_MISMATCH', 'OCR_LOW_QUALITY', 'OCR_FIELD_DISAGREEMENT',
  'CONFLICTING_POLICY_LIMITS', 'PREAUTHORIZATION_REQUIRED', 'LATE_SUBMISSION', 'PER_DAY_LIMIT', 'PROMPT_INJECTION_SUSPECTED',
]);

export function FlagList({ flags }) {
  if (!flags?.length) return null;
  return (
    <div className="flag-list">
      {flags.map((flag) => (
        <span key={flag} className={`flag ${BLOCKING.has(flag) ? 'flag--warn' : ''}`} title={flag}>
          {FLAG_LABELS[flag] || flag.replace(/_/g, ' ').toLowerCase()}
        </span>
      ))}
    </div>
  );
}

export function ScoreBar({ label, value }) {
  const percent = Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
  return (
    <div className="score-bar">
      <div className="score-bar__label"><span>{label}</span><strong>{percent}%</strong></div>
      <div className="score-bar__track"><div className="score-bar__fill" style={{ width: `${percent}%` }} /></div>
    </div>
  );
}

export function Citations({ citations }) {
  if (!citations?.length) return null;
  return (
    <ol className="citation-list">
      {citations.map((citation) => (
        <li key={`${citation.id}-${citation.chunk_id}`} className="citation">
          <div className="citation__head">
            <span className="citation__id">[{citation.id}]</span>
            <strong>{citation.title}</strong>
            <span className="muted-text">
              v{citation.policy_version}
              {citation.section ? ` · ${citation.section}` : ''}
              {citation.page_start ? ` · p.${citation.page_start}` : ''}
            </span>
          </div>
          <p>{citation.snippet}</p>
        </li>
      ))}
    </ol>
  );
}
