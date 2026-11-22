import { PolicyAssistant } from '../components/PolicyAssistant';
import { SectionCard } from '../components/SectionCard';

export function AssistantPage() {
  return (
    <div className="upload-layout">
      <SectionCard title="Ask about your coverage" subtitle="Policy assistant">
        <PolicyAssistant />
      </SectionCard>
      <aside className="card upload-help">
        <p className="eyebrow">How answers work</p>
        <h2>Grounded in your policies</h2>
        <ul>
          <li>Answers come only from active reimbursement policies and cite the clause, version and page.</li>
          <li>Add a bill amount to get a coverage estimate based on the policy limit.</li>
          <li>Estimates do not include amounts you have already claimed this year or document checks.</li>
          <li>If the policies do not cover your question, the assistant says so instead of guessing.</li>
        </ul>
      </aside>
    </div>
  );
}
