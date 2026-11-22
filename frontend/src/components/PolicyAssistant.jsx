import { useState } from 'react';

import { api } from '../api';
import { Citations, FlagList, errorMessage, formatMoney } from './ui';

const EXAMPLES = [
  'Is root canal treatment covered and what is the limit?',
  'Will a ₹30,000 MRI scan be reimbursed?',
  'Are cosmetic procedures excluded?',
  'What documents do I need to submit?',
];

export function PolicyAssistant() {
  const [question, setQuestion] = useState('');
  const [amount, setAmount] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const ask = async (text) => {
    const value = (text ?? question).trim();
    if (value.length < 3) {
      setError('Please type a question about your reimbursement policy.');
      return;
    }
    setQuestion(value);
    setLoading(true);
    setError('');
    try {
      const payload = { question: value };
      if (amount) payload.amount = Number(amount);
      const response = await api.post('/rag/ask', payload);
      setResult(response.data);
    } catch (askError) {
      setError(errorMessage(askError, 'The assistant is unavailable right now.'));
    } finally {
      setLoading(false);
    }
  };

  const estimate = result?.coverage_estimate;

  return (
    <div className="assistant">
      <form className="stack" onSubmit={(event) => { event.preventDefault(); ask(); }}>
        <label>
          Your question
          <textarea
            rows={3}
            value={question}
            maxLength={1000}
            placeholder="e.g. Is physiotherapy covered and up to how much per year?"
            onChange={(event) => setQuestion(event.target.value)}
          />
        </label>
        <div className="assistant__row">
          <label>
            Bill amount (optional)
            <input type="number" min="1" step="1" value={amount} placeholder="₹" onChange={(event) => setAmount(event.target.value)} />
          </label>
          <button type="submit" disabled={loading}>{loading ? 'Searching policies…' : 'Ask'}</button>
        </div>
        <div className="chip-row">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="chip secondary" onClick={() => ask(example)} disabled={loading}>{example}</button>
          ))}
        </div>
      </form>

      {error ? <p className="error-text" role="alert">{error}</p> : null}

      {result ? (
        <div className="answer" aria-live="polite">
          {estimate?.estimated_decision ? (
            <div className="estimate">
              <span className="eyebrow">Coverage estimate · {estimate.category}</span>
              <strong>{estimate.estimated_decision}: {formatMoney(estimate.estimated_reimbursement)} of {formatMoney(estimate.claimed_amount)}</strong>
              <span className="muted-text">
                Limit {formatMoney(estimate.limit_amount)}{estimate.limit_period ? ` per ${estimate.limit_period}` : ''}. {estimate.note}.
              </span>
            </div>
          ) : null}
          <pre className="answer__text">
            {estimate?.estimated_decision
              ? result.answer.split('\n').filter((line) => !line.startsWith('Estimate:')).join('\n')
              : result.answer}
          </pre>
          <div className="answer__meta">
            <span className="muted-text">
              {result.mode === 'llm' ? 'AI answer grounded in policy text' : result.mode === 'extractive' ? 'Quoted from policy text' : 'No matching policy'}
              {' · '}relevance {Math.round(result.confidence * 100)}%
            </span>
            <FlagList flags={result.flags} />
          </div>
          <Citations citations={result.citations} />
        </div>
      ) : null}
    </div>
  );
}
