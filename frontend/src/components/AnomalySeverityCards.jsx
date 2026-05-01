function AnomalySeverityCards({ anomalies }) {
  const breakdown = anomalies?.severity_breakdown || {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0
  };

  const blocks = [
    { label: "Critical", value: breakdown.critical || 0, tone: "text-rose-700 border-rose-200 bg-rose-50" },
    { label: "High", value: breakdown.high || 0, tone: "text-orange-700 border-orange-200 bg-orange-50" },
    { label: "Medium", value: breakdown.medium || 0, tone: "text-amber-700 border-amber-200 bg-amber-50" },
    { label: "Low", value: breakdown.low || 0, tone: "text-emerald-700 border-emerald-200 bg-emerald-50" }
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {blocks.map((block) => (
        <article key={block.label} className={`glass-card border p-4 ${block.tone}`}>
          <p className="text-xs uppercase tracking-wide opacity-80">{block.label}</p>
          <p className="mt-2 font-display text-2xl font-semibold">{block.value.toLocaleString()}</p>
        </article>
      ))}
    </div>
  );
}

export default AnomalySeverityCards;
