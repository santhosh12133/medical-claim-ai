import { PolicyAssistant } from '../components/PolicyAssistant';
import { PageHeader, Panel } from '../components/ui';

export function AssistantPage({ audience = 'employee' }) {
  return (
    <>
      <PageHeader
        title="Coverage questions"
        description={audience === 'admin'
          ? 'Ask what the active policies say. Answers quote the clause they come from.'
          : 'Ask what your policy covers before you submit a bill. Answers quote the clause they come from.'}
      />
      <div className="split split--form">
        <Panel title={null}>
          <PolicyAssistant />
        </Panel>
        <Panel title="About these answers" className="panel--quiet">
          <ul className="plain-list">
            <li>Answers use only the active reimbursement policies, and show the policy, version and page.</li>
            <li>Add a bill amount for an estimate of what would be reimbursed.</li>
            <li>The estimate doesn’t include what you’ve already claimed this year, or checks on the bill itself.</li>
            <li>If no policy covers the question, the answer says so.</li>
          </ul>
        </Panel>
      </div>
    </>
  );
}
