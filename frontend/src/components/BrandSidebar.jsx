function BrandSidebar({ dataset, profile, anomalies }) {
  return (
    <aside className="glass-card sticky top-5 h-[calc(100vh-2.5rem)] w-full max-w-[320px] p-5">
      <div className="mb-8 flex items-center gap-3">
        <img
          src="/anomira-logo.svg"
          alt="Anomira logo"
          className="h-11 w-11 rounded-xl border border-sky-200/30 object-cover shadow-[0_0_30px_rgba(80,170,255,0.45)]"
        />
        <div>
          <h1 className="font-display text-xl font-semibold text-slate-700">Anomira</h1>
          <p className="text-xs text-slate-600">Automatic Data Intelligence &amp; Anomaly Detection System</p>
        </div>
      </div>

      <div className="space-y-3 text-sm">
        <div className="rounded-xl border border-slate-200 bg-white/70 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Dataset</p>
          <p className="mt-1 truncate text-slate-700">{dataset?.filename || "No dataset loaded"}</p>
          {dataset ? <p className="mt-1 text-xs text-slate-500">ID: {dataset.dataset_id.slice(0, 12)}...</p> : null}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white/70 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Rows / Columns</p>
          <p className="mt-1 text-lg font-semibold text-slate-700">
            {profile ? `${profile.row_count.toLocaleString()} / ${profile.column_count}` : "-"}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white/70 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Suspicious Records</p>
          <p className="mt-1 text-lg font-semibold text-rose-600">{anomalies?.suspicious_count ?? 0}</p>
        </div>
      </div>

      <div className="mt-8 space-y-2 text-sm text-slate-700">
        <p className="metric-chip">Upload</p>
        <p className="metric-chip">Profile</p>
        <p className="metric-chip">Detect</p>
        <p className="metric-chip">Report</p>
      </div>
    </aside>
  );
}

export default BrandSidebar;
