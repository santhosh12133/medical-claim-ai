export function SectionCard({ title, subtitle, children }) {
  return (
    <section className="card">
      <div className="card-header">
        <div>
          <p className="eyebrow">{subtitle}</p>
          <h2>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}
