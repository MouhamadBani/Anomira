import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import SectionCard from "./SectionCard";

function AnomalyScoreChart({ distribution }) {
  const data = (distribution || []).map((item, idx) => ({
    index: idx + 1,
    row: Number(item.row_index),
    score: Number(item.score)
  }));

  return (
    <SectionCard title="Anomaly Score Curve" subtitle="Ranked anomaly scores from highest to lowest">
      {!data.length ? (
        <p className="text-sm text-slate-600">Run anomaly detection to visualize scores.</p>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer>
            <AreaChart data={data} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
              <defs>
                <linearGradient id="anomalyFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f97316" stopOpacity={0.68} />
                  <stop offset="100%" stopColor="#f97316" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.28)" vertical={false} />
              <XAxis dataKey="index" tick={{ fill: "#334155", fontSize: 11 }} />
              <YAxis domain={[0, 1]} tick={{ fill: "#334155", fontSize: 11 }} />
              <Tooltip
                formatter={(value) => Number(value).toFixed(3)}
                labelFormatter={(value) => `Rank ${value}`}
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid rgba(251, 146, 60, 0.35)",
                  borderRadius: "12px"
                }}
              />
              <Area type="monotone" dataKey="score" stroke="#f97316" strokeWidth={2} fill="url(#anomalyFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </SectionCard>
  );
}

export default AnomalyScoreChart;
