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

function MissingValuesChart({ missingValues }) {
  const data = Object.entries(missingValues || {})
    .map(([column, stats]) => ({
      column,
      missingPct: Number(stats?.pct || 0)
    }))
    .filter((item) => item.missingPct > 0)
    .sort((a, b) => b.missingPct - a.missingPct)
    .slice(0, 12);

  return (
    <SectionCard title="Missing Values" subtitle="Columns with highest missing-value ratios">
      {!data.length ? (
        <p className="text-sm text-slate-600">No missing values detected or profile unavailable.</p>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer>
            <BarChart data={data} margin={{ top: 8, right: 18, left: 0, bottom: 48 }}>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.28)" vertical={false} />
              <XAxis
                dataKey="column"
                angle={-25}
                textAnchor="end"
                interval={0}
                tick={{ fill: "#334155", fontSize: 11 }}
              />
              <YAxis tick={{ fill: "#334155", fontSize: 11 }} unit="%" />
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid rgba(148, 163, 184, 0.4)",
                  borderRadius: "12px"
                }}
              />
              <Bar dataKey="missingPct" fill="url(#missingGradient)" radius={[8, 8, 0, 0]} />
              <defs>
                <linearGradient id="missingGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38bdf8" />
                  <stop offset="100%" stopColor="#2563eb" />
                </linearGradient>
              </defs>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </SectionCard>
  );
}

export default MissingValuesChart;
