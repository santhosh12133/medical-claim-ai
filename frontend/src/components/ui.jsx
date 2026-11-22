import { useEffect } from 'react';

import { Icon } from './Icon';

// ------------------------------------------------------------------ formatting
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

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(String(value).length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
}

export function errorMessage(error, fallback = 'Something went wrong. Try again.') {
  if (!error?.response) return 'The server could not be reached. Check your connection and try again.';
  const detail = error.response.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(', ');
  return fallback;
}

// ------------------------------------------------------------------ claim status
const STATUS = {
  approved: { tone: 'approved', label: 'Approved' },
  'partially approved': { tone: 'partial', label: 'Partially approved' },
  rejected: { tone: 'rejected', label: 'Rejected' },
  'needs attention': { tone: 'review', label: 'Needs review' },
  'needs human review': { tone: 'review', label: 'Needs review' },
  'pending review': { tone: 'waiting', label: 'Awaiting review' },
  processing: { tone: 'processing', label: 'Processing' },
  pending: { tone: 'processing', label: 'Processing' },
  active: { tone: 'approved', label: 'Active' },
  inactive: { tone: 'waiting', label: 'Inactive' },
  archived: { tone: 'processing', label: 'Archived' },
};

export function statusInfo(status) {
  return STATUS[String(status || '').toLowerCase()] || { tone: 'processing', label: status || 'Processing' };
}

export const isFinal = (status) => ['approved', 'partially approved', 'rejected'].includes(String(status || '').toLowerCase());

// Kept for callers that only need the class name.
export const statusClass = (status) => `badge badge--${statusInfo(status).tone}`;

export function StatusBadge({ status }) {
  const { tone, label } = statusInfo(status);
  return <span className={`badge badge--${tone}`}>{label}</span>;
}

/** The decision mark: drawn like an ink stamp on a processed bill. */
export function Stamp({ status, amount, compact = false }) {
  const { tone, label } = statusInfo(status);
  return (
    <span className={`stamp stamp--${tone} ${compact ? 'stamp--compact' : ''}`} role="img"
      aria-label={`${label}${amount != null ? ` ${formatMoney(amount)}` : ''}`}>
      <span className="stamp__label">{label}</span>
      {amount != null && tone !== 'rejected' && tone !== 'review' ? <span className="stamp__amount">{formatMoney(amount)}</span> : null}
    </span>
  );
}

// ------------------------------------------------------------------ flags
// label: short name for reviewers; explain: plain sentence for the employee.
const FLAGS = {
  DUPLICATE_DOCUMENT: ['Duplicate document', 'This file was already submitted.'],
  DUPLICATE_INVOICE: ['Duplicate invoice', 'A bill with this invoice number was already claimed.'],
  FUTURE_DATED_BILL: ['Future-dated bill', 'The bill date is later than today.'],
  STALE_BILL: ['Old bill', 'The bill is older than the policy usually allows.'],
  PATIENT_NAME_MISMATCH: ['Patient name differs', 'The patient name on the bill is different from the name on your account.'],
  OCR_LOW_QUALITY: ['Hard-to-read scan', 'Parts of the bill were hard to read.'],
  OCR_FIELD_DISAGREEMENT: ['Unclear amount or treatment', 'The amount or treatment could not be read with certainty.'],
  CONFLICTING_POLICY_LIMITS: ['Conflicting policy limits', 'Two policies set different limits for this treatment.'],
  PREAUTHORIZATION_REQUIRED: ['Pre-authorisation required', 'This treatment needs approval before it happens.'],
  LATE_SUBMISSION: ['Late submission', 'The bill was submitted after the policy deadline.'],
  PER_DAY_LIMIT: ['Per-day limit', 'The policy limits this treatment per day.'],
  PARTIAL_APPROVAL: ['Partial approval', 'The bill is above the policy limit, so part of it is covered.'],
  LIMIT_EXHAUSTED: ['Limit used up', 'This year’s limit for the treatment has been used.'],
  ANNUAL_LIMIT_APPLIED: ['Annual limit applied', 'Earlier claims this year reduced the amount available.'],
  EXCLUSION_MATCHED: ['Policy exclusion', 'The policy excludes this treatment.'],
  COPAY_APPLIED: ['Co-pay applied', 'A co-payment was deducted.'],
  NO_POLICY_FOUND: ['No policy found', 'No active policy covers this treatment.'],
  LIMIT_NOT_FOUND: ['Limit not found', 'The policy does not state a limit for this treatment.'],
  LOW_CONFIDENCE: ['Low confidence', 'The automatic check was not certain enough to decide.'],
  AMOUNT_MISMATCH: ['Amount differs', 'The amount entered differs from the bill total.'],
  GPT_UNAVAILABLE: ['AI check unavailable', 'The optional AI check did not run; the policy check decided.'],
  PROMPT_INJECTION_SUSPECTED: ['Suspicious text', 'The document contains unusual instructions.'],
};

const BLOCKING = new Set([
  'DUPLICATE_DOCUMENT', 'DUPLICATE_INVOICE', 'FUTURE_DATED_BILL', 'PATIENT_NAME_MISMATCH', 'OCR_LOW_QUALITY',
  'OCR_FIELD_DISAGREEMENT', 'CONFLICTING_POLICY_LIMITS', 'PREAUTHORIZATION_REQUIRED', 'LATE_SUBMISSION', 'PER_DAY_LIMIT',
  'PROMPT_INJECTION_SUSPECTED', 'AMOUNT_MISMATCH',
]);

const HIDDEN_FROM_EMPLOYEES = new Set(['GPT_UNAVAILABLE', 'LOW_CONFIDENCE', 'BLOCKING_FLAG']);

export const flagLabel = (flag) => FLAGS[flag]?.[0] || flag.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

export function FlagList({ flags }) {
  const visible = (flags || []).filter((flag) => flag !== 'BLOCKING_FLAG');
  if (!visible.length) return null;
  return (
    <ul className="flag-list" aria-label="Flags">
      {visible.map((flag) => (
        <li key={flag} className={`flag ${BLOCKING.has(flag) ? 'flag--warn' : ''}`} title={FLAGS[flag]?.[1] || flag}>
          {BLOCKING.has(flag) ? <Icon name="alert" size={13} /> : null}
          {flagLabel(flag)}
        </li>
      ))}
    </ul>
  );
}

/** Flags explained in a sentence each, for the employee who submitted the claim. */
export function FlagExplanations({ flags }) {
  const visible = (flags || []).filter((flag) => !HIDDEN_FROM_EMPLOYEES.has(flag) && FLAGS[flag]);
  if (!visible.length) return null;
  return (
    <ul className="flag-notes">
      {visible.map((flag) => <li key={flag}><Icon name="alert" size={15} />{FLAGS[flag][1]}</li>)}
    </ul>
  );
}

// ------------------------------------------------------------------ layout pieces
export function PageHeader({ title, description, actions }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description ? <p className="page-header__description">{description}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function Panel({ title, description, actions, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      {title ? (
        <header className="panel__header">
          <div>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          {actions ? <div className="panel__actions">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function EmptyState({ icon = 'claims', title, children, action }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon"><Icon name={icon} size={22} /></span>
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}

export function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onClose, 4000);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);
  if (!toast) return null;
  return (
    <div className={`toast toast--${toast.type}`} role="status" aria-live="polite">
      <Icon name={toast.type === 'error' ? 'alert' : 'check'} size={18} />
      <div className="toast__content">
        <p className="toast__title">{toast.title}</p>
        {toast.message ? <p className="toast__message">{toast.message}</p> : null}
      </div>
      <button type="button" className="icon-button" onClick={onClose} aria-label="Dismiss"><Icon name="close" size={16} /></button>
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
            <span className="citation__id">{citation.id}</span>
            <strong>{citation.title}</strong>
            <span className="citation__where">
              Version {citation.policy_version}
              {citation.section ? `, ${citation.section}` : ''}
              {citation.page_start ? `, page ${citation.page_start}` : ''}
            </span>
          </div>
          <p>{citation.snippet}</p>
        </li>
      ))}
    </ol>
  );
}
