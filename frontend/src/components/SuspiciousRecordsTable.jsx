import SectionCard from "./SectionCard";

function prettify(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function categoryTone(category) {
  if (category === "time_series") {
    return "border-indigo-200 bg-indigo-50 text-indigo-700";
  }
  if (category === "collective") {
    return "border-purple-200 bg-purple-50 text-purple-700";
  }
  if (category === "contextual") {
    return "border-cyan-200 bg-cyan-50 text-cyan-700";
  }
  if (category === "multivariate") {
    return "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700";
  }
  if (category === "geospatial") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  return "border-sky-200 bg-sky-50 text-sky-700";
}

function SuspiciousRecordsTable({ records }) {
  const keys = records?.length ? Object.keys(records[0].record || {}).slice(0, 4) : [];

  return (
    <SectionCard
      title="Suspicious Records"
      subtitle="Top anomalies ranked by combined score"
      className="overflow-hidden"
    >
      {!records?.length ? (
        <p className="text-sm text-slate-600">No suspicious records found yet.</p>
      ) : (
        <div className="soft-scrollbar overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-100/80">
              <tr>
                <th className="px-3 py-2 text-slate-700">Row</th>
                <th className="px-3 py-2 text-slate-700">Score</th>
                <th className="px-3 py-2 text-slate-700">Severity</th>
                <th className="px-3 py-2 text-slate-700">Category</th>
                <th className="px-3 py-2 text-slate-700">Anomaly Types</th>
                <th className="px-3 py-2 text-slate-700">Affected Columns</th>
                <th className="px-3 py-2 text-slate-700">Sample Values</th>
                <th className="px-3 py-2 text-slate-700">Explanation</th>
              </tr>
            </thead>
            <tbody>
              {records.map((item) => (
                <tr key={`${item.row_index}-${item.anomaly_score}`} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-700">{item.row_index}</td>
                  <td className="px-3 py-2 text-slate-700">{item.anomaly_score}</td>
                  <td className="px-3 py-2">
                    <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-700">
                      {item.severity}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full border px-2 py-1 text-xs font-semibold ${categoryTone(item.primary_category)}`}>
                      {prettify(item.primary_category || "point_global")}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-700">
                    {item.anomaly_types?.length
                      ? item.anomaly_types.slice(0, 4).map((type) => prettify(type)).join(", ")
                      : "-"}
                  </td>
                  <td className="px-3 py-2 text-slate-700">{item.affected_columns?.join(", ") || "-"}</td>
                  <td className="px-3 py-2 text-slate-700">
                    {keys.map((key) => `${key}: ${item.record?.[key] ?? "-"}`).join(" | ")}
                  </td>
                  <td className="max-w-[380px] px-3 py-2 text-slate-700">{item.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

export default SuspiciousRecordsTable;
