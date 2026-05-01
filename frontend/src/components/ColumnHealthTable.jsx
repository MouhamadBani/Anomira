import SectionCard from "./SectionCard";

const statusClasses = {
  healthy: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  critical: "border-rose-200 bg-rose-50 text-rose-700"
};

function ColumnHealthTable({ columnHealth }) {
  return (
    <SectionCard title="Column Health" subtitle="Data type, quality status, and detected issues" className="overflow-hidden">
      {!columnHealth?.length ? (
        <p className="text-sm text-slate-600">Run profiling to view column diagnostics.</p>
      ) : (
        <div className="soft-scrollbar overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-100/80">
              <tr>
                <th className="px-3 py-2 text-slate-700">Column</th>
                <th className="px-3 py-2 text-slate-700">Type</th>
                <th className="px-3 py-2 text-slate-700">Missing %</th>
                <th className="px-3 py-2 text-slate-700">Unique</th>
                <th className="px-3 py-2 text-slate-700">Status</th>
                <th className="px-3 py-2 text-slate-700">Issues</th>
              </tr>
            </thead>
            <tbody>
              {columnHealth.map((item) => (
                <tr key={item.column} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-700">{item.column}</td>
                  <td className="px-3 py-2 text-slate-700">{item.type}</td>
                  <td className="px-3 py-2 text-slate-700">{item.missing_pct}%</td>
                  <td className="px-3 py-2 text-slate-700">{item.unique_count}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded-full border px-2 py-1 text-xs font-semibold ${statusClasses[item.status] || statusClasses.warning}`}
                    >
                      {item.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-700">{item.issues?.length ? item.issues.join("; ") : "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

export default ColumnHealthTable;
