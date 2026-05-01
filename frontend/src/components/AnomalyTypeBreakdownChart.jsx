import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import SectionCard from "./SectionCard";

function prettify(label) {
  return label.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function AnomalyTypeBreakdownChart({ anomalyTypeBreakdown }) {
  const data = Object.entries(anomalyTypeBreakdown || {})
    .map(([type, count]) => ({
      type: prettify(type),
      count: Number(count || 0)
    }))
    .filter((item) => item.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 14);

  return (
    <SectionCard title="Anomaly Type Classification" subtitle="Automatic classification across required anomaly families">
      {!data.length ? (
        <p className="text-sm text-slate-600">Run analysis to view anomaly type distribution.</p>
      ) : (
        <div className="h-80 w-full">
          <ResponsiveContainer>
            <BarChart data={data} layout="vertical" margin={{ top: 6, right: 24, left: 12, bottom: 6 }}>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.28)" horizontal={false} />
              <XAxis type="number" tick={{ fill: "#334155", fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="type"
                width={280}
                tick={{ fill: "#334155", fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid rgba(148, 163, 184, 0.4)",
                  borderRadius: "12px"
                }}
              />
              <Bar dataKey="count" fill="url(#typeGrad)" radius={[0, 8, 8, 0]} />
              <defs>
                <linearGradient id="typeGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#3b82f6" />
                  <stop offset="100%" stopColor="#06b6d4" />
                </linearGradient>
              </defs>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </SectionCard>
  );
}

export default AnomalyTypeBreakdownChart;
