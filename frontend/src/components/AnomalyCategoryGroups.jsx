import SectionCard from "./SectionCard";

function prettify(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function severityTone(severity) {
  if (severity === "critical") {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  if (severity === "high") {
    return "border-orange-200 bg-orange-50 text-orange-700";
  }
  if (severity === "medium") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function shortText(value, max = 160) {
  const text = String(value || "");
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max)}...`;
}

function AnomalyCategoryGroups({ groups }) {
  const safeGroups = Array.isArray(groups) ? groups : [];

  return (
    <SectionCard
      title="Grouped Anomaly Categories"
      subtitle="Categorized view of anomalies so you can understand what kind of issue happened and where to focus first."
    >
      {!safeGroups.length ? (
        <p className="text-sm text-slate-600">Run analysis to view grouped anomaly categories.</p>
      ) : (
        <div className="space-y-4">
          {safeGroups.map((group) => {
            const severity = group?.severity_breakdown || {};
            const topColumns = Array.isArray(group?.top_affected_columns) ? group.top_affected_columns : [];
            const signals = Array.isArray(group?.anomaly_signals) ? group.anomaly_signals : [];
            const sampleRecords = Array.isArray(group?.sample_records) ? group.sample_records : [];
            return (
              <article key={group.category_key} className="rounded-2xl border border-slate-200 bg-white/80 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display text-base font-semibold text-slate-700">{group.category_label}</h3>
                    <p className="mt-1 text-sm text-slate-600">{group.description}</p>
                  </div>
                  <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-right">
                    <p className="font-display text-xl font-semibold text-sky-700">{Number(group.count || 0).toLocaleString()}</p>
                    <p className="text-xs uppercase tracking-wide text-sky-700">{group.count_label || "records"}</p>
                  </div>
                </div>

                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Severity Mix</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {Object.entries(severity)
                        .filter(([, count]) => Number(count || 0) > 0)
                        .map(([key, count]) => (
                          <span key={`${group.category_key}-${key}`} className={`rounded-full border px-2 py-1 text-xs font-semibold ${severityTone(key)}`}>
                            {prettify(key)}: {Number(count).toLocaleString()}
                          </span>
                        ))}
                      {!Object.entries(severity).some(([, count]) => Number(count || 0) > 0) ? (
                        <span className="text-xs text-slate-500">No severity distribution for this category.</span>
                      ) : null}
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Top Affected Columns</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {topColumns.length ? (
                        topColumns.map((item) => (
                          <span key={`${group.category_key}-${item.column}`} className="metric-chip">
                            {item.column} ({Number(item.count || 0).toLocaleString()})
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-slate-500">No column concentration detected.</span>
                      )}
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Top Signals</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {signals.length ? (
                        signals.map((signal) => (
                          <span key={`${group.category_key}-${signal.signal}`} className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-1 text-xs font-semibold text-cyan-700">
                            {prettify(signal.label || signal.signal)} ({Number(signal.count || 0).toLocaleString()})
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-slate-500">No signal details available.</span>
                      )}
                    </div>
                  </div>
                </div>

                {sampleRecords.length ? (
                  <div className="soft-scrollbar mt-3 overflow-auto rounded-xl border border-slate-200">
                    <table className="min-w-full text-left text-sm">
                      <thead className="border-b border-slate-200 bg-slate-100/80">
                        <tr>
                          <th className="px-3 py-2 text-slate-700">Row</th>
                          <th className="px-3 py-2 text-slate-700">Score</th>
                          <th className="px-3 py-2 text-slate-700">Severity</th>
                          <th className="px-3 py-2 text-slate-700">Signals</th>
                          <th className="px-3 py-2 text-slate-700">Why</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sampleRecords.map((record) => (
                          <tr key={`${group.category_key}-${record.row_index}-${record.anomaly_score}`} className="border-b border-slate-100 hover:bg-slate-50">
                            <td className="px-3 py-2 text-slate-700">{record.row_index}</td>
                            <td className="px-3 py-2 text-slate-700">{record.anomaly_score}</td>
                            <td className="px-3 py-2">
                              <span className={`rounded-full border px-2 py-1 text-xs font-semibold ${severityTone(record.severity)}`}>
                                {record.severity}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-slate-700">
                              {(record.anomaly_types || []).slice(0, 3).map((item) => prettify(item)).join(", ") || "-"}
                            </td>
                            <td className="max-w-[520px] px-3 py-2 text-slate-700">{shortText(record.explanation, 180)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

export default AnomalyCategoryGroups;
