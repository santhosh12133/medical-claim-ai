import { Icon } from './Icon';
import { FlagExplanations, Stamp, StatusBadge, formatDate, formatMoney, isFinal } from './ui';

export const claimTitle = (claim) => claim.treatment || 'Medical bill';

export function decidedAmount(claim) {
  if (claim.final_approved_amount != null) return claim.final_approved_amount;
  return null;
}

/** One claim as a ledger row: what, where, when, how much, and where it stands. */
export function ClaimRow({ claim, expanded, onToggle, showEmployee = false }) {
  const Tag = onToggle ? 'button' : 'div';
  return (
    <Tag type={onToggle ? 'button' : undefined} className={`claim-row ${expanded ? 'claim-row--open' : ''}`}
      onClick={onToggle} aria-expanded={onToggle ? Boolean(expanded) : undefined}>
      <span className="claim-row__what">
        <strong>{claimTitle(claim)}</strong>
        <span>{showEmployee ? `${claim.employee_name}, ` : ''}{claim.hospital_name || 'Hospital not read'}</span>
      </span>
      <span className="claim-row__when">{formatDate(claim.claim_date || claim.created_at)}</span>
      <span className="claim-row__amount">{formatMoney(claim.amount)}</span>
      <span className="claim-row__status"><StatusBadge status={claim.status} /></span>
      {onToggle ? <Icon name="chevron" size={16} className="claim-row__chevron" /> : null}
    </Tag>
  );
}

function stageOf(claim) {
  if (isFinal(claim.status)) return 3;
  if (['completed', 'failed'].includes(claim.processing_status) || claim.policy_decision) return 2;
  return 1;
}

export function ClaimTimeline({ claim }) {
  const stage = stageOf(claim);
  const waiting = !isFinal(claim.status) && stage === 2;
  const steps = [
    { label: 'Submitted', detail: formatDate(claim.created_at) },
    { label: 'Read and checked', detail: stage >= 2 ? 'Against the reimbursement policy' : 'In progress' },
    { label: 'Decision', detail: isFinal(claim.status) ? (claim.reviewed_at ? 'By a reviewer' : 'Made automatically') : waiting ? 'With a reviewer' : 'Pending' },
  ];
  return (
    <ol className="timeline" aria-label="Claim progress">
      {steps.map((step, index) => {
        const state = stage > index + 1 || (index === 2 && stage === 3) ? 'done' : stage === index + 1 ? 'current' : 'todo';
        return (
          <li key={step.label} className={`timeline__step timeline__step--${state}`}>
            <span className="timeline__dot">{state === 'done' ? <Icon name="check" size={13} /> : index + 1}</span>
            <span className="timeline__text"><strong>{step.label}</strong><span>{step.detail}</span></span>
          </li>
        );
      })}
    </ol>
  );
}

/** What was read from the bill. */
export function ExtractedFields({ claim, reading = false }) {
  const pending = (value) => value ?? (reading ? 'Reading…' : 'Not found');
  return (
    <dl className="detail-grid">
      <div><dt>Treatment</dt><dd>{pending(claim.treatment)}</dd></div>
      <div><dt>Hospital</dt><dd>{pending(claim.hospital_name)}</dd></div>
      <div><dt>Bill total</dt><dd className="num">{claim.amount != null ? formatMoney(claim.amount) : pending(null)}</dd></div>
      <div><dt>Bill date</dt><dd>{claim.claim_date ? formatDate(claim.claim_date) : pending(null)}</dd></div>
      <div><dt>Invoice number</dt><dd>{pending(claim.invoice_number)}</dd></div>
      <div><dt>Patient</dt><dd>{pending(claim.patient_name)}</dd></div>
    </dl>
  );
}

/** The decision area for the employee: the stamp, the reason, and what to do next. */
export function ClaimOutcome({ claim }) {
  const final = isFinal(claim.status);
  const amount = final ? decidedAmount(claim) ?? claim.policy_approved_amount : null;
  return (
    <div className="outcome">
      <Stamp status={claim.status} amount={amount} />
      <div className="outcome__text">
        {final ? (
          <p>{claim.reviewer_notes || claim.policy_reason || 'Your claim has been decided.'}</p>
        ) : claim.status === 'Needs Attention' ? (
          <p>A reviewer will look at this claim. You don’t need to do anything unless they contact you.</p>
        ) : claim.status === 'Pending Review' ? (
          <p>The policy check is done{claim.policy_decision ? `, recommending ${claim.policy_decision.toLowerCase()}` : ''}.
            A reviewer will confirm it.</p>
        ) : (
          <p>Your bill is being read and checked. This usually takes under a minute.</p>
        )}
        <FlagExplanations flags={claim.risk_flags_json} />
      </div>
    </div>
  );
}
