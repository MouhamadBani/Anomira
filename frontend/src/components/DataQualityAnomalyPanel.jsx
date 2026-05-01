import SectionCard from "./SectionCard";

function DataQualityAnomalyPanel({ qualityAnomalies }) {
  const entries = Object.entries(qualityAnomalies || {}).map(([issue, payload]) => ({
    issue,
    count: Number(payload?.count || 0),
    columns: payload?.columns || []
  }));

  return (
    <SectionCard title="Data Quality Anomalies" subtitle="Missing, duplicates, impossible values, category inconsistencies, skew, and invalid dates">
      {!entries.length ? (
        <p className="text-sm text-slate-600">No data quality anomaly summary available.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {entries.map((item) => (
            <article key={item.issue} className="rounded-xl border border-slate-200 bg-white/80 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-500">{item.issue.replace(/_/g, " ")}</p>
              <p className="mt-1 font-display text-xl font-semibold text-slate-700">{item.count.toLocaleString()}</p>
              <p className="mt-1 text-xs text-slate-500">
                {item.columns.length ? `Columns: ${item.columns.slice(0, 4).join(", ")}` : "Columns: -"}
              </p>
            </article>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

export default DataQualityAnomalyPanel;
