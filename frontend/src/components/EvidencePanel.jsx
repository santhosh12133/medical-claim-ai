import { FlagList, ScoreBar, formatMoney, statusClass } from './ui';

export function EvidencePanel({ verification }) {
  if (!verification) return null;
  const rule = verification.extracted_rule;
  const breakdown = verification.confidence_breakdown || {};

  return (
    <div className="evidence">
      <div className="evidence__summary">
        <div>
          <p className="eyebrow">Policy recommendation{verification.autonomous ? ' · auto-decided' : ''}</p>
          <div className="evidence__decision">
            <span className={statusClass(verification.status)}>{verification.status}</span>
            <strong>{formatMoney(verification.approved_amount)}</strong>
            {verification.category ? <span className="muted-text">{verification.category}</span> : null}
          </div>
          <p className="hint">{verification.reason}</p>
          <FlagList flags={verification.flags} />
        </div>
        <div className="evidence__scores">
          <ScoreBar label="Overall confidence" value={verification.confidence} />
          {breakdown.retrieval_relevance != null ? <ScoreBar label="Retrieval relevance" value={breakdown.retrieval_relevance} /> : null}
          {breakdown.rule_confidence != null ? <ScoreBar label="Rule extraction" value={breakdown.rule_confidence} /> : null}
          {breakdown.evidence_consistency != null ? <ScoreBar label="Evidence consistency" value={breakdown.evidence_consistency} /> : null}
        </div>
      </div>

      {rule ? (
        <div className="rule-grid">
          <div><span>Limit</span><strong>{formatMoney(rule.limit_amount)}{rule.limit_period ? ` / ${rule.limit_period}` : ''}</strong></div>
          <div><span>Co-pay</span><strong>{rule.copay_percent ? `${rule.copay_percent}%` : '—'}</strong></div>
          <div><span>Reimbursed at</span><strong>{rule.reimbursement_percent ? `${rule.reimbursement_percent}%` : '100%'}</strong></div>
          <div><span>Pre-auth</span><strong>{rule.requires_preauthorization ? 'Required' : 'No'}</strong></div>
          <div><span>Deadline</span><strong>{rule.submission_deadline_days ? `${rule.submission_deadline_days} days` : '—'}</strong></div>
          <div><span>Exclusion</span><strong>{rule.matched_exclusion ? 'Applies' : 'None'}</strong></div>
        </div>
      ) : null}

      <blockquote className="clause">
        {verification.policy_used}
        <cite>{verification.policy_source}</cite>
      </blockquote>

      {verification.retrieved_policies?.length ? (
        <details className="evidence__details">
          <summary>Retrieved evidence ({verification.retrieved_policies.length}) · {verification.retrieval?.mode || 'hybrid'} search{verification.latency_ms ? ` · ${verification.latency_ms} ms` : ''}</summary>
          <ol className="citation-list">
            {verification.retrieved_policies.map((hit) => (
              <li key={hit.chunk_id} className="citation">
                <div className="citation__head">
                  <strong>{hit.title}</strong>
                  <span className="muted-text">
                    {hit.policy_type} v{hit.policy_version}{hit.page_start ? ` · p.${hit.page_start}` : ''}
                    {' · '}relevance {Math.round(hit.similarity * 100)}%
                    {hit.vector_score != null ? ` · vector ${hit.vector_score.toFixed(2)}` : ''}
                    {hit.lexical_score != null ? ` · bm25 ${hit.lexical_score.toFixed(2)}` : ''}
                  </span>
                </div>
                <p>{hit.chunk_text}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}

      {verification.decision_trace?.length ? (
        <details className="evidence__details">
          <summary>Decision trace</summary>
          <ol className="trace">
            {verification.decision_trace.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}
          </ol>
        </details>
      ) : null}
    </div>
  );
}
