function SectionCard({ title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`glass-card p-5 ${className}`}>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-slate-700">{title}</h2>
          {subtitle ? <p className="mt-1 text-sm text-slate-600">{subtitle}</p> : null}
        </div>
        {actions ? <div>{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

export default SectionCard;
