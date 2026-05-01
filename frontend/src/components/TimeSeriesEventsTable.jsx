import SectionCard from "./SectionCard";

const TYPE_DEFINITIONS = {
  time_series_spike:
    "Sudden upward jump above local rolling baseline beyond threshold.",
  time_series_dip:
    "Sudden downward drop below local rolling baseline beyond threshold.",
  time_series_trend_change:
    "Abrupt local slope/trajectory change versus recent trend behavior.",
  time_series_seasonal_break:
    "Departure from expected repeating seasonal pattern at lagged interval."
};

function formatType(value) {
  return String(value || "-").replace(/_/g, " ");
}

function buildEvidence(event) {
  if (event.evidence) {
    return event.evidence;
  }

  const m = event.metrics || {};
  const parts = [];
  if (m.current_value !== undefined && m.current_value !== null) {
    parts.push(`current=${m.current_value}`);
  }
  if (m.local_baseline !== undefined && m.local_baseline !== null) {
    parts.push(`baseline=${m.local_baseline}`);
  }
  if (m.seasonal_expected !== undefined && m.seasonal_expected !== null) {
    parts.push(`expected=${m.seasonal_expected}`);
  }
  if (m.threshold !== undefined && m.threshold !== null) {
    parts.push(`threshold=${m.threshold}`);
  }
  if (m.threshold_ratio !== undefined && m.threshold_ratio !== null) {
    parts.push(`ratio=${m.threshold_ratio}x`);
  }
  return parts.join(", ") || "-";
}

function TimeSeriesEventsTable({ events }) {
  return (
    <SectionCard
      title="Time-Series Anomaly Events"
      subtitle="Detected spikes, dips, trend changes, and seasonal breaks with exact evidence"
      className="overflow-hidden"
    >
      {!events?.length ? (
        <p className="text-sm text-slate-600">No time-series events detected or no date column available.</p>
      ) : (
        <div className="soft-scrollbar overflow-auto">
          <table className="min-w-[1450px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-100/80">
              <tr>
                <th className="px-3 py-2 text-slate-700">Type</th>
                <th className="px-3 py-2 text-slate-700">Definition</th>
                <th className="px-3 py-2 text-slate-700">What Happened</th>
                <th className="px-3 py-2 text-slate-700">Evidence</th>
                <th className="px-3 py-2 text-slate-700">Row</th>
                <th className="px-3 py-2 text-slate-700">Column</th>
                <th className="px-3 py-2 text-slate-700">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {events.slice(0, 60).map((event, idx) => (
                <tr key={`${event.row_index}-${event.anomaly_type}-${idx}`} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-medium text-slate-700">
                    {event.type_label || formatType(event.anomaly_type)}
                  </td>
                  <td className="max-w-[280px] px-3 py-2 text-slate-600">
                    {event.definition || TYPE_DEFINITIONS[event.anomaly_type] || "-"}
                  </td>
                  <td className="max-w-[420px] px-3 py-2 text-slate-700">
                    {event.what_happened || "-"}
                  </td>
                  <td className="max-w-[380px] px-3 py-2 text-slate-600">
                    {buildEvidence(event)}
                  </td>
                  <td className="px-3 py-2 text-slate-700">{event.row_index}</td>
                  <td className="px-3 py-2 text-slate-700">{event.column || "-"}</td>
                  <td className="px-3 py-2 text-slate-700">{event.timestamp || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

export default TimeSeriesEventsTable;
