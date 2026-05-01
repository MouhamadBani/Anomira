import SectionCard from "./SectionCard";

function DataPreviewTable({ rows }) {
  const columns = rows?.length ? Object.keys(rows[0]) : [];

  return (
    <SectionCard title="Data Preview" subtitle="First 10 rows after ingestion" className="overflow-hidden">
      {!rows?.length ? (
        <p className="text-sm text-slate-600">Upload a dataset to preview records.</p>
      ) : (
        <div className="soft-scrollbar overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-100/80">
              <tr>
                {columns.map((col) => (
                  <th key={col} className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                  {columns.map((col) => (
                    <td key={`${idx}-${col}`} className="max-w-[220px] truncate px-3 py-2 text-slate-700">
                      {row[col] === null || row[col] === undefined || row[col] === "" ? "-" : String(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

export default DataPreviewTable;
