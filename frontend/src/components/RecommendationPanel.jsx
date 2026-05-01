import SectionCard from "./SectionCard";

function RecommendationPanel({ recommendations, autoFixPlan }) {
  return (
    <SectionCard title="Recommendations & Auto-Fix Plan" subtitle="Action plan based on profile and anomaly signals">
      {!recommendations?.length ? (
        <p className="text-sm text-slate-600">Run analysis to generate recommendations.</p>
      ) : (
        <ol className="mb-4 space-y-3 text-sm text-slate-700">
          {recommendations.map((item, idx) => (
            <li key={`${idx}-${item.slice(0, 20)}`} className="rounded-xl border border-slate-200 bg-white/70 p-3">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-sky-100 font-semibold text-sky-700">
                {idx + 1}
              </span>
              {item}
            </li>
          ))}
        </ol>
      )}

      {autoFixPlan?.length ? (
        <div className="soft-scrollbar overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-100/80">
              <tr>
                <th className="px-3 py-2 text-slate-700">Issue</th>
                <th className="px-3 py-2 text-slate-700">Columns</th>
                <th className="px-3 py-2 text-slate-700">Recommended Action</th>
                <th className="px-3 py-2 text-slate-700">Auto-Fix Safe</th>
                <th className="px-3 py-2 text-slate-700">Expected Impact</th>
              </tr>
            </thead>
            <tbody>
              {autoFixPlan.map((item, idx) => (
                <tr key={`${item.issue}-${idx}`} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-700">{item.issue}</td>
                  <td className="px-3 py-2 text-slate-700">{item.columns?.length ? item.columns.join(", ") : "-"}</td>
                  <td className="px-3 py-2 text-slate-700">{item.recommended_action}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded-full border px-2 py-1 text-xs font-semibold ${
                        item.auto_fix_safe
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "border-amber-200 bg-amber-50 text-amber-700"
                      }`}
                    >
                      {item.auto_fix_safe ? "Yes" : "Needs Review"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-700">{item.expected_impact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </SectionCard>
  );
}

export default RecommendationPanel;
