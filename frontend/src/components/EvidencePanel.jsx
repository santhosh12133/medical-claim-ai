import { FlagList, ScoreBar, Stamp, formatMoney } from './ui';

export function EvidencePanel({ verification }) {
  if (!verification) return null;
  const rule = verification.extracted_rule;
  const breakdown = verification.confidence_breakdown || {};

  return (
    <section className="evidence" aria-label="Policy check">
      <div className="evidence__summary">
        <div className="evidence__verdict">
          <Stamp status={verification.status} amount={verification.approved_amount} compact />
          <div>
            <p className="evidence__reason">{verification.reason}</p>
            <p className="evidence__how">
              {verification.autonomous ? 'Decided automatically.' : 'Recommendation for a reviewer.'}
              {verification.category ? ` Category: ${verification.category}.` : ''}
            </p>
            <FlagList flags={verification.flags} />
          </div>
        </div>
        <div className="evidence__scores">
          <ScoreBar label="Confidence" value={verification.confidence} />
          {breakdown.retrieval_relevance != null ? <ScoreBar label="Policy match" value={breakdown.retrieval_relevance} /> : null}
          {breakdown.rule_confidence != null ? <ScoreBar label="Rule reading" value={breakdown.rule_confidence} /> : null}
          {breakdown.evidence_consistency != null ? <ScoreBar label="Evidence agreement" value={breakdown.evidence_consistency} /> : null}
        </div>
      </div>

      {rule ? (
        <dl className="rule-grid">
          <div><dt>Limit</dt><dd>{formatMoney(rule.limit_amount)}{rule.limit_period ? ` a ${rule.limit_period}` : ''}</dd></div>
          <div><dt>Co-pay</dt><dd>{rule.copay_percent ? `${rule.copay_percent}%` : 'None'}</dd></div>
          <div><dt>Reimbursed at</dt><dd>{rule.reimbursement_percent ? `${rule.reimbursement_percent}%` : '100%'}</dd></div>
          <div><dt>Pre-authorisation</dt><dd>{rule.requires_preauthorization ? 'Required' : 'Not required'}</dd></div>
          <div><dt>Deadline</dt><dd>{rule.submission_deadline_days ? `${rule.submission_deadline_days} days` : 'None stated'}</dd></div>
          <div><dt>Exclusion</dt><dd>{rule.matched_exclusion ? 'Applies' : 'None'}</dd></div>
        </dl>
      ) : null}

      {verification.policy_used ? (
        <blockquote className="clause">
          <p>{verification.policy_used}</p>
          <cite>{verification.policy_source}</cite>
        </blockquote>
      ) : null}

      {verification.retrieved_policies?.length ? (
        <details className="disclosure">
          <summary>Policy passages considered ({verification.retrieved_policies.length})</summary>
          <ol className="citation-list">
            {verification.retrieved_policies.map((hit, index) => (
              <li key={hit.chunk_id} className="citation">
                <div className="citation__head">
                  <span className="citation__id">{index + 1}</span>
                  <strong>{hit.title}</strong>
                  <span className="citation__where">
                    Version {hit.policy_version}{hit.page_start ? `, page ${hit.page_start}` : ''}, {Math.round(hit.similarity * 100)}% match
                  </span>
                </div>
                <p>{hit.chunk_text}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}

      {verification.decision_trace?.length ? (
        <details className="disclosure">
          <summary>Decision steps</summary>
          <ol className="steps steps--plain">
            {verification.decision_trace.map((step, index) => <li key={`${index}-${step}`}><span>{step}</span></li>)}
          </ol>
        </details>
      ) : null}
    </section>
  );
}
