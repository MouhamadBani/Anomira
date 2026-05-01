import SectionCard from "./SectionCard";

function GisSummaryPanel({ geospatialSummary }) {
  if (!geospatialSummary || !Object.keys(geospatialSummary).length) {
    return (
      <SectionCard title="GIS Summary" subtitle="Geospatial detection and coordinate quality checks">
        <p className="text-sm text-slate-600">Run profiling to inspect GIS readiness.</p>
      </SectionCard>
    );
  }

  if (!geospatialSummary.has_geospatial_data) {
    return (
      <SectionCard title="GIS Summary" subtitle="Geospatial detection and coordinate quality checks">
        <p className="text-sm text-slate-600">No GIS coordinate pair or geometry column detected.</p>
      </SectionCard>
    );
  }

  const bbox = geospatialSummary.bbox || {};
  const hasBbox = Object.keys(bbox).length > 0;
  const geometryColumns = geospatialSummary.geometry_columns || [];

  return (
    <SectionCard title="GIS Summary" subtitle="Detected geospatial fields, coverage, and coordinate quality">
      <div className="grid gap-3 md:grid-cols-2">
        <article className="rounded-xl border border-slate-200 bg-white/80 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Coordinate Columns</p>
          <p className="mt-1 text-sm text-slate-700">
            Lat: <span className="font-semibold">{geospatialSummary.latitude_column || "-"}</span> | Lon:{" "}
            <span className="font-semibold">{geospatialSummary.longitude_column || "-"}</span>
          </p>
          <p className="mt-2 text-xs text-slate-600">
            Valid pairs: {Number(geospatialSummary.valid_coordinate_pairs || 0).toLocaleString()} | Invalid pairs:{" "}
            {Number(geospatialSummary.invalid_coordinate_pairs || 0).toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            Missing pairs: {Number(geospatialSummary.missing_coordinate_pairs || 0).toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            Invalid lat/lon values: {Number(geospatialSummary.invalid_latitude_values || 0).toLocaleString()} /{" "}
            {Number(geospatialSummary.invalid_longitude_values || 0).toLocaleString()}
          </p>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white/80 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Spatial Envelope</p>
          {hasBbox ? (
            <p className="mt-1 text-xs text-slate-700">
              lat[{bbox.min_lat}, {bbox.max_lat}] lon[{bbox.min_lon}, {bbox.max_lon}]
            </p>
          ) : (
            <p className="mt-1 text-xs text-slate-600">No valid bounding box available yet.</p>
          )}
          <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">Geometry Columns</p>
          <p className="mt-1 text-xs text-slate-700">
            {geometryColumns.length ? geometryColumns.join(", ") : "None detected"}
          </p>
        </article>
      </div>
    </SectionCard>
  );
}

export default GisSummaryPanel;
