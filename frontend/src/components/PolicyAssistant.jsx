import { useState } from 'react';

import { api } from '../api';
import { Icon } from './Icon';
import { Citations, FlagList, errorMessage, formatMoney } from './ui';

const EXAMPLES = [
  'Is root canal treatment covered, and what is the limit?',
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
      setError('Type a question about what the policy covers.');
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
      setError(errorMessage(askError, 'Answers aren’t available right now. Try again in a minute.'));
    } finally {
      setLoading(false);
    }
  };

  const estimate = result?.coverage_estimate;
  const answerText = estimate?.estimated_decision
    ? result.answer.split('\n').filter((line) => !line.startsWith('Estimate:')).join('\n')
    : result?.answer;

  return (
    <div className="assistant">
      <form className="form" onSubmit={(event) => { event.preventDefault(); ask(); }}>
        <label className="field">
          <span className="field__label">Your question</span>
          <textarea rows={3} value={question} maxLength={1000}
            placeholder="For example, is physiotherapy covered, and up to how much a year?"
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) ask(); }} />
        </label>
        <div className="form-row form-row--end">
          <label className="field">
            <span className="field__label">Bill amount <span className="field__optional">optional</span></span>
            <input type="number" inputMode="decimal" min="1" step="1" value={amount} placeholder="₹"
              onChange={(event) => setAmount(event.target.value)} />
          </label>
          <button type="submit" className="button button--primary" disabled={loading}>{loading ? 'Searching the policies…' : 'Ask'}</button>
        </div>
        <div className="chip-row" aria-label="Example questions">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="chip" onClick={() => ask(example)} disabled={loading}>{example}</button>
          ))}
        </div>
      </form>

      {error ? <p className="form-error" role="alert"><Icon name="alert" size={16} />{error}</p> : null}

      {result ? (
        <article className="answer" aria-live="polite">
          {estimate?.estimated_decision ? (
            <div className="estimate">
              <span className="estimate__label">Estimate for {estimate.category}</span>
              <strong>{estimate.estimated_decision}: {formatMoney(estimate.estimated_reimbursement)} of {formatMoney(estimate.claimed_amount)}</strong>
              <span className="estimate__note">
                Limit {formatMoney(estimate.limit_amount)}{estimate.limit_period ? ` a ${estimate.limit_period}` : ''}. {estimate.note}.
              </span>
            </div>
          ) : null}
          <p className="answer__text">{answerText}</p>
          <div className="answer__meta">
            <span>
              {result.mode === 'llm' ? 'Written by AI from the policy text below' : result.mode === 'extractive' ? 'Quoted from the policy text below' : 'No policy covers this question'}
            </span>
            <FlagList flags={result.flags} />
          </div>
          <Citations citations={result.citations} />
        </article>
      ) : null}
    </div>
  );
}
