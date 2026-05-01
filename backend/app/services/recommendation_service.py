from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional


def generate_auto_fix_plan(
    profile: Dict[str, Any],
    anomaly_payload: Dict[str, Any],
    expected_columns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    column_types = profile.get("column_types", {})

    if expected_columns:
        missing_required = [col for col in expected_columns if col not in column_types]
        if missing_required:
            plan.append(
                {
                    "issue": "Missing required variables",
                    "columns": missing_required,
                    "recommended_action": "Map or rename source columns to expected variables before running dependent analysis.",
                    "auto_fix_safe": False,
                    "expected_impact": "High impact: required analytics or validations remain blocked until resolved.",
                }
            )

    missing_values = profile.get("missing_values", {})
    for col, stats in missing_values.items():
        missing_pct = float(stats.get("pct", 0.0))
        if missing_pct <= 0:
            continue

        col_type = column_types.get(col, "unknown")
        if missing_pct < 5:
            action = "Drop rows with missing values for this field."
            impact = "Low impact: minimal data loss with cleaner records."
            safe = True
        elif missing_pct <= 30:
            impute = "median" if col_type == "numeric" else "mode/default"
            action = f"Impute with {impute} and add a 'was_missing_{col}' indicator column."
            impact = "Medium impact: preserves volume while adding missingness traceability."
            safe = True
        else:
            action = "Treat as high risk; drop this column unless it is business-critical."
            impact = "High impact: can materially change model reliability and report quality."
            safe = False

        plan.append(
            {
                "issue": "Missing values",
                "columns": [col],
                "recommended_action": action,
                "auto_fix_safe": safe,
                "expected_impact": impact,
            }
        )

    duplicate_rows = int(profile.get("duplicate_rows", 0))
    if duplicate_rows > 0:
        plan.append(
            {
                "issue": "Duplicate rows",
                "columns": [],
                "recommended_action": "Remove exact duplicates and keep the first occurrence; apply key-based dedupe if a business key exists.",
                "auto_fix_safe": True,
                "expected_impact": "Medium impact: reduces repeated noise in anomaly and trend calculations.",
            }
        )

    invalid_dates = profile.get("invalid_dates", {})
    for col, count in invalid_dates.items():
        if int(count) <= 0:
            continue
        plan.append(
            {
                "issue": "Invalid dates",
                "columns": [col],
                "recommended_action": "Parse with known date formats, convert unresolved values to null, and standardize valid output to YYYY-MM-DD.",
                "auto_fix_safe": True,
                "expected_impact": "Medium impact: restores time-based analyses and prevents date parsing failures.",
            }
        )

    geospatial_summary = profile.get("geospatial_summary", {})
    lat_col = geospatial_summary.get("latitude_column")
    lon_col = geospatial_summary.get("longitude_column")
    invalid_geo_count = int(
        geospatial_summary.get("invalid_coordinate_pairs", 0)
        + geospatial_summary.get("missing_coordinate_pairs", 0)
        + geospatial_summary.get("invalid_latitude_values", 0)
        + geospatial_summary.get("invalid_longitude_values", 0)
    )
    if invalid_geo_count > 0:
        geo_columns = [col for col in [lat_col, lon_col] if col]
        plan.append(
            {
                "issue": "Invalid GIS coordinates",
                "columns": geo_columns,
                "recommended_action": "Normalize CRS inputs, clip latitude/longitude to valid ranges, and backfill missing coordinate pairs from trusted geocoding sources.",
                "auto_fix_safe": False,
                "expected_impact": "High impact: improves map analytics quality and geospatial anomaly reliability.",
            }
        )

    constant_columns = profile.get("constant_columns", [])
    if constant_columns:
        plan.append(
            {
                "issue": "Constant columns",
                "columns": constant_columns,
                "recommended_action": "Drop constant columns because they provide no discriminatory information.",
                "auto_fix_safe": True,
                "expected_impact": "Low impact: simplifies dataset and can improve model stability.",
            }
        )

    high_cardinality = profile.get("high_cardinality_columns", [])
    if high_cardinality:
        plan.append(
            {
                "issue": "High-cardinality categories",
                "columns": high_cardinality,
                "recommended_action": "Group rare categories into 'Other' and consider frequency/hash encoding for modeling.",
                "auto_fix_safe": False,
                "expected_impact": "Medium impact: improves generalization but may reduce category granularity.",
            }
        )

    skewed_cols = profile.get("skewed_numeric_columns", {})
    if skewed_cols:
        plan.append(
            {
                "issue": "Skewed numeric distributions",
                "columns": list(skewed_cols.keys()),
                "recommended_action": "Apply log1p transform or robust scaling for downstream statistical/modeling workflows.",
                "auto_fix_safe": False,
                "expected_impact": "Medium impact: improves model fit and metric stability.",
            }
        )

    outlier_counts = profile.get("outlier_counts", {})
    outlier_columns = [col for col, count in outlier_counts.items() if int(count) > 0]
    if outlier_columns:
        plan.append(
            {
                "issue": "Outliers and extreme values",
                "columns": outlier_columns,
                "recommended_action": "Validate source values, then cap/winsorize impossible extremes or null-and-impute when errors are confirmed.",
                "auto_fix_safe": False,
                "expected_impact": "High impact: directly affects anomaly precision and downstream metrics.",
            }
        )

    type_mismatch_counts = profile.get("type_mismatch_counts", {})
    mismatch_columns = [col for col, count in type_mismatch_counts.items() if int(count) > 0]
    if mismatch_columns:
        plan.append(
            {
                "issue": "Type mismatches",
                "columns": mismatch_columns,
                "recommended_action": "Auto-cast safe values to the target type; move non-castable entries to null and track mismatch counts in QA logs.",
                "auto_fix_safe": False,
                "expected_impact": "Medium impact: improves schema consistency while preserving auditability.",
            }
        )

    suspicious_count = int(anomaly_payload.get("suspicious_count", 0))
    if suspicious_count > 0:
        counter = Counter()
        for record in anomaly_payload.get("records", []):
            counter.update(record.get("affected_columns", []))
        most_common = [col for col, _ in counter.most_common(5)]
        plan.append(
            {
                "issue": "Suspicious anomaly records",
                "columns": most_common,
                "recommended_action": "Prioritize manual review for high-severity records and verify source-system audit trails before auto-correction.",
                "auto_fix_safe": False,
                "expected_impact": "High impact: reduces risk of propagating invalid records.",
            }
        )

    if not plan:
        plan.append(
            {
                "issue": "No major data quality issues detected",
                "columns": [],
                "recommended_action": "Keep current validation rules and continue routine monitoring.",
                "auto_fix_safe": True,
                "expected_impact": "Low impact: maintain quality baseline.",
            }
        )

    return plan


def generate_recommendations(
    profile: Dict[str, Any],
    anomaly_payload: Dict[str, Any],
    expected_columns: Optional[List[str]] = None,
) -> List[str]:
    recommendations: List[str] = []

    if expected_columns:
        missing_required = [col for col in expected_columns if col not in profile.get("column_types", {})]
        if missing_required:
            recommendations.append(
                f"Required variables are missing: {', '.join(missing_required[:6])}. Map/rename source fields before dependent analysis."
            )

    duplicate_rows = int(profile.get("duplicate_rows", 0))
    if duplicate_rows > 0:
        recommendations.append(
            f"Remove or merge {duplicate_rows} duplicate rows to prevent repeated signals in downstream analysis."
        )

    missing_values = profile.get("missing_values", {})
    missing_cols = [
        (col, stats.get("pct", 0.0))
        for col, stats in missing_values.items()
        if stats.get("pct", 0.0) > 0
    ]
    missing_cols.sort(key=lambda item: item[1], reverse=True)
    if missing_cols:
        top_cols = ", ".join([f"{col} ({pct:.1f}%)" for col, pct in missing_cols[:4]])
        recommendations.append(
            f"Address missing data in: {top_cols}. Use median for numeric fields and mode or domain defaults for categorical fields."
        )

    constant_columns = profile.get("constant_columns", [])
    if constant_columns:
        recommendations.append(
            f"Drop or repurpose constant columns: {', '.join(constant_columns[:5])}. They add noise without predictive value."
        )

    high_cardinality = profile.get("high_cardinality_columns", [])
    if high_cardinality:
        recommendations.append(
            f"Review high-cardinality fields ({', '.join(high_cardinality[:4])}) and consider grouping rare categories or hashing for modeling."
        )

    invalid_dates = profile.get("invalid_dates", {})
    problematic_dates = [col for col, count in invalid_dates.items() if count > 0]
    if problematic_dates:
        recommendations.append(
            f"Fix invalid date formats in columns: {', '.join(problematic_dates[:4])}. Standardize to ISO-8601 where possible."
        )

    geospatial_summary = profile.get("geospatial_summary", {})
    lat_col = geospatial_summary.get("latitude_column")
    lon_col = geospatial_summary.get("longitude_column")
    invalid_geo_count = int(
        geospatial_summary.get("invalid_coordinate_pairs", 0)
        + geospatial_summary.get("missing_coordinate_pairs", 0)
        + geospatial_summary.get("invalid_latitude_values", 0)
        + geospatial_summary.get("invalid_longitude_values", 0)
    )
    if invalid_geo_count > 0 and lat_col and lon_col:
        recommendations.append(
            f"Resolve {invalid_geo_count} GIS coordinate issues in {lat_col}/{lon_col}; validate CRS, ranges (lat -90..90, lon -180..180), and fill missing coordinate pairs."
        )

    type_mismatch_counts = profile.get("type_mismatch_counts", {})
    mismatch_cols = [col for col, count in type_mismatch_counts.items() if count > 0]
    if mismatch_cols:
        recommendations.append(
            f"Resolve type mismatches in: {', '.join(mismatch_cols[:4])}. Cast valid entries and move invalid values to null for controlled imputation."
        )

    skewed_cols = profile.get("skewed_numeric_columns", {})
    if skewed_cols:
        recommendations.append(
            "Consider log-transforming or winsorizing skewed numeric features before advanced modeling."
        )

    outlier_counts = profile.get("outlier_counts", {})
    outlier_columns = [col for col, count in outlier_counts.items() if count > 0]
    if outlier_columns:
        recommendations.append(
            f"Validate extreme values in: {', '.join(outlier_columns[:5])}. Confirm units and cap impossible values."
        )

    records = anomaly_payload.get("records", [])
    if records:
        counter = Counter()
        for record in records:
            counter.update(record.get("affected_columns", []))
        most_common = [col for col, _ in counter.most_common(4)]
        if most_common:
            recommendations.append(
                f"Prioritize manual review for suspicious records concentrated in: {', '.join(most_common)}."
            )

    if int(anomaly_payload.get("suspicious_count", 0)) == 0:
        recommendations.append("No high-risk anomalies were detected. Continue with routine quality checks and monitoring.")

    if not recommendations:
        recommendations.append("Dataset quality looks stable. Maintain current data validation rules and monitor new ingestions.")

    return recommendations
