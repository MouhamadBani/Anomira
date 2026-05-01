from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List


def _load_logo_data_url() -> str:
    root = Path(__file__).resolve().parents[3]
    public_dir = root / "frontend" / "public"
    candidates = [
        ("anomira-logo.svg", "image/svg+xml"),
        ("anomira-logo.jpg", "image/jpeg"),
    ]

    for filename, mime in candidates:
        logo_path = public_dir / filename
        if logo_path.exists():
            encoded = base64.b64encode(logo_path.read_bytes()).decode("utf-8")
            return f"data:{mime};base64,{encoded}"

    return ""


def _render_key_value_rows(data: Dict[str, Any]) -> str:
    rows = []
    for key, value in data.items():
        rows.append(
            "<tr>"
            f"<td>{escape(str(key))}</td>"
            f"<td>{escape(str(value))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_recommendations(recommendations: List[str]) -> str:
    return "\n".join([f"<li>{escape(item)}</li>" for item in recommendations])


def _render_records_table(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "<p>No suspicious records were flagged.</p>"

    rows: List[str] = []
    for record in records[:30]:
        rows.append(
            "<tr>"
            f"<td>{record['row_index']}</td>"
            f"<td>{record['anomaly_score']}</td>"
            f"<td>{escape(record['severity'])}</td>"
            f"<td>{escape(', '.join(record.get('anomaly_types', [])[:4]))}</td>"
            f"<td>{escape(', '.join(record['affected_columns'][:4]))}</td>"
            f"<td>{escape(record.get('explanation', '-'))}</td>"
            f"<td>{escape(record['recommended_action'])}</td>"
            "</tr>"
        )

    return (
        "<table><thead><tr><th>Row</th><th>Score</th><th>Severity</th><th>Types</th><th>Affected Columns</th><th>Why It Is Anomalous</th><th>Action</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_anomaly_type_breakdown(breakdown: Dict[str, Any]) -> str:
    if not breakdown:
        return "<p>No anomaly type breakdown available.</p>"

    rows = []
    for key, value in breakdown.items():
        rows.append(
            "<tr>"
            f"<td>{escape(str(key))}</td>"
            f"<td>{escape(str(value))}</td>"
            "</tr>"
        )

    return "<table><thead><tr><th>Anomaly Type</th><th>Count</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _render_quality_anomalies(quality: Dict[str, Any]) -> str:
    if not quality:
        return "<p>No quality anomalies found.</p>"

    rows = []
    for issue, payload in quality.items():
        count = payload.get("count", 0)
        cols = payload.get("columns", [])
        rows.append(
            "<tr>"
            f"<td>{escape(str(issue))}</td>"
            f"<td>{escape(str(count))}</td>"
            f"<td>{escape(', '.join(cols[:6]) if cols else '-')}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>Issue</th><th>Count</th><th>Columns</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _render_anomaly_groups(groups: List[Dict[str, Any]]) -> str:
    if not groups:
        return "<p>No grouped anomaly categories available.</p>"

    rows: List[str] = []
    for group in groups:
        severity = group.get("severity_breakdown", {}) or {}
        severity_text = ", ".join([f"{k}:{v}" for k, v in severity.items() if int(v) > 0]) or "-"
        top_cols = ", ".join([item.get("column", "") for item in group.get("top_affected_columns", [])[:6] if item.get("column")]) or "-"
        top_signals = ", ".join([item.get("label", item.get("signal", "")) for item in group.get("anomaly_signals", [])[:6]]) or "-"
        rows.append(
            "<tr>"
            f"<td>{escape(str(group.get('category_label', group.get('category_key', '-'))))}</td>"
            f"<td>{escape(str(group.get('count', 0)))} {escape(str(group.get('count_label', 'records')))}</td>"
            f"<td>{escape(severity_text)}</td>"
            f"<td>{escape(top_cols)}</td>"
            f"<td>{escape(top_signals)}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>Category</th><th>Count</th><th>Severity Mix</th><th>Top Columns</th><th>Top Signals</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _render_geospatial_summary(summary: Dict[str, Any]) -> str:
    if not summary or not summary.get("has_geospatial_data"):
        return "<p>No geospatial coordinate pair or geometry data detected.</p>"

    bbox = summary.get("bbox", {}) or {}
    bbox_text = (
        f"lat[{bbox.get('min_lat')}, {bbox.get('max_lat')}] lon[{bbox.get('min_lon')}, {bbox.get('max_lon')}]"
        if bbox
        else "-"
    )
    rows = [
        ("Latitude column", summary.get("latitude_column", "-")),
        ("Longitude column", summary.get("longitude_column", "-")),
        ("Valid coordinate pairs", summary.get("valid_coordinate_pairs", 0)),
        ("Invalid coordinate pairs", summary.get("invalid_coordinate_pairs", 0)),
        ("Missing coordinate pairs", summary.get("missing_coordinate_pairs", 0)),
        ("Invalid latitude values", summary.get("invalid_latitude_values", 0)),
        ("Invalid longitude values", summary.get("invalid_longitude_values", 0)),
        ("Geometry columns", ", ".join(summary.get("geometry_columns", [])) or "-"),
        ("Bounding box", bbox_text),
    ]

    rendered = []
    for key, value in rows:
        rendered.append(f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>")

    return "<table><thead><tr><th>GIS Metric</th><th>Value</th></tr></thead><tbody>" + "".join(rendered) + "</tbody></table>"


def _render_time_events(events: List[Dict[str, Any]]) -> str:
    if not events:
        return "<p>No time-series anomaly events detected.</p>"

    rows = []
    for event in events[:40]:
        event_type = event.get("type_label") or event.get("anomaly_type", "-")
        definition = event.get("definition", "-")
        what_happened = event.get("what_happened", "-")
        evidence = event.get("evidence", "-")
        rows.append(
            "<tr>"
            f"<td>{escape(str(event_type))}</td>"
            f"<td>{escape(str(definition))}</td>"
            f"<td>{escape(str(what_happened))}</td>"
            f"<td>{escape(str(evidence))}</td>"
            f"<td>{escape(str(event.get('row_index', '-')))}</td>"
            f"<td>{escape(str(event.get('column', '-')))}</td>"
            f"<td>{escape(str(event.get('timestamp', '-')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Type</th><th>Definition</th><th>What Happened</th><th>Evidence</th><th>Row</th><th>Column</th><th>Timestamp</th></tr></thead>"
        + "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_auto_fix_plan(plan: List[Dict[str, Any]]) -> str:
    if not plan:
        return "<p>No auto-fix plan generated.</p>"

    rows: List[str] = []
    for item in plan:
        columns = ", ".join(item.get("columns", [])) or "-"
        safe_text = "Yes" if item.get("auto_fix_safe") else "Needs Review"
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('issue', '-')))}</td>"
            f"<td>{escape(columns)}</td>"
            f"<td>{escape(str(item.get('recommended_action', '-')))}</td>"
            f"<td>{escape(safe_text)}</td>"
            f"<td>{escape(str(item.get('expected_impact', '-')))}</td>"
            "</tr>"
        )

    return (
        "<table><thead><tr><th>Issue</th><th>Columns</th><th>Recommended Action</th><th>Auto-Fix Safe</th><th>Expected Impact</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def generate_html_report(
    filename: str,
    profile: Dict[str, Any],
    anomalies: Dict[str, Any],
    recommendations: List[str],
    auto_fix_plan: List[Dict[str, Any]],
) -> str:
    logo_data_url = _load_logo_data_url()
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    summary = {
        "Filename": filename,
        "Rows": profile.get("row_count", 0),
        "Columns": profile.get("column_count", 0),
        "Duplicate Rows": profile.get("duplicate_rows", 0),
        "Suspicious Records": anomalies.get("suspicious_count", 0),
        "Report Generated": generated_at,
    }

    missing_map = profile.get("missing_values", {})
    missing_top = dict(
        sorted(
            {k: f"{v.get('pct', 0)}%" for k, v in missing_map.items()}.items(),
            key=lambda item: float(str(item[1]).replace("%", "")),
            reverse=True,
        )[:10]
    )

    severity_breakdown = anomalies.get("severity_breakdown", {})
    anomaly_type_breakdown = anomalies.get("anomaly_type_breakdown", {})
    quality_anomalies = anomalies.get("quality_anomalies", {})
    anomaly_groups = anomalies.get("anomaly_groups", [])
    time_series_events = anomalies.get("time_series_events", [])
    geospatial_summary = profile.get("geospatial_summary", {})

    logo_html = (
        f'<img src="{logo_data_url}" alt="Anomira Logo" class="logo" />'
        if logo_data_url
        else ""
    )

    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Anomira Data Intelligence Report</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      font-family: 'Segoe UI', sans-serif;
      background: linear-gradient(165deg, #f7fbff, #edf4ff);
      color: #17253b;
    }}
    .container {{
      max-width: 1100px;
      margin: 40px auto;
      padding: 24px;
    }}
    .header {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 24px;
    }}
    .logo {{
      width: 42px;
      height: 42px;
      border-radius: 10px;
      object-fit: cover;
      box-shadow: 0 0 18px rgba(110, 173, 255, 0.35);
    }}
    .tagline {{
      color: #50729b;
      font-size: 13px;
      margin-top: 4px;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid rgba(129, 160, 200, 0.30);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 18px;
      backdrop-filter: blur(8px);
    }}
    h1, h2 {{
      margin: 0 0 10px 0;
    }}
    h2 {{
      font-size: 18px;
      color: #1f477a;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }}
    th, td {{
      border-bottom: 1px solid rgba(148,163,184,0.28);
      padding: 10px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{
      color: #2e5f9d;
      font-weight: 600;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    li {{
      margin-bottom: 8px;
    }}
    .pill {{
      display: inline-block;
      margin-right: 8px;
      margin-bottom: 8px;
      background: rgba(96, 165, 250, 0.14);
      border: 1px solid rgba(96, 165, 250, 0.34);
      color: #1e3a5f;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"header\">
      {logo_html}
      <div>
        <h1>Anomira</h1>
        <div class=\"tagline\">Automatic Data Intelligence &amp; Anomaly Detection System</div>
      </div>
    </div>

    <div class=\"card\">
      <h2>Dataset Summary</h2>
      <table>
        <tbody>
          {_render_key_value_rows(summary)}
        </tbody>
      </table>
    </div>

    <div class=\"card\">
      <h2>Severity Breakdown</h2>
      {''.join([f'<span class="pill">{escape(str(k))}: {escape(str(v))}</span>' for k, v in severity_breakdown.items()])}
    </div>

    <div class=\"card\">
      <h2>Grouped Anomaly Categories</h2>
      {_render_anomaly_groups(anomaly_groups)}
    </div>

    <div class=\"card\">
      <h2>Anomaly Type Breakdown</h2>
      {_render_anomaly_type_breakdown(anomaly_type_breakdown)}
    </div>

    <div class=\"card\">
      <h2>Data Quality Anomalies</h2>
      {_render_quality_anomalies(quality_anomalies)}
    </div>

    <div class=\"card\">
      <h2>GIS Summary</h2>
      {_render_geospatial_summary(geospatial_summary)}
    </div>

    <div class=\"card\">
      <h2>Time-Series Events</h2>
      {_render_time_events(time_series_events)}
    </div>

    <div class=\"card\">
      <h2>Top Missing Value Columns</h2>
      <table>
        <tbody>
          {_render_key_value_rows(missing_top)}
        </tbody>
      </table>
    </div>

    <div class=\"card\">
      <h2>Recommended Fixes</h2>
      <ul>
        {_render_recommendations(recommendations)}
      </ul>
    </div>

    <div class=\"card\">
      <h2>Auto-Fix Plan</h2>
      {_render_auto_fix_plan(auto_fix_plan)}
    </div>

    <div class=\"card\">
      <h2>Suspicious Records (Top 30)</h2>
      {_render_records_table(anomalies.get('records', []))}
    </div>
  </div>
</body>
</html>
"""
