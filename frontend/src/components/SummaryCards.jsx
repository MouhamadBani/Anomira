function SummaryCards({ dataset, profile, anomalies }) {
  const cards = [
    {
      title: "Rows",
      value: profile?.row_count ?? dataset?.row_count ?? 0,
      tone: "text-sky-700"
    },
    {
      title: "Columns",
      value: profile?.column_count ?? dataset?.column_count ?? 0,
      tone: "text-cyan-700"
    },
    {
      title: "Duplicates",
      value: profile?.duplicate_rows ?? 0,
      tone: "text-amber-700"
    },
    {
      title: "Suspicious",
      value: anomalies?.suspicious_count ?? 0,
      tone: "text-rose-700"
    }
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <article key={card.title} className="glass-card p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">{card.title}</p>
          <p className={`mt-2 font-display text-2xl font-semibold ${card.tone}`}>{card.value.toLocaleString()}</p>
        </article>
      ))}
    </div>
  );
}

export default SummaryCards;
