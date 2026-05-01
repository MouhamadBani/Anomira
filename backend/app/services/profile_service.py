from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype


def _looks_identifier(series: pd.Series, col_name: str) -> bool:
    values = series.dropna()
    if values.empty:
        return False

    name_hint = any(token in col_name.lower() for token in ["id", "uuid", "key", "code"])
    unique_ratio = values.nunique(dropna=True) / max(len(values), 1)

    if is_numeric_dtype(values):
        integer_like = np.isclose(values.astype(float) % 1, 0).mean() > 0.95
        return unique_ratio > 0.9 and integer_like and (name_hint or values.nunique() > 25)

    sample = values.astype(str).head(300)
    alnum_ratio = sample.str.match(r"^[A-Za-z0-9_\-]+$").mean()
    avg_len = sample.str.len().mean()

    return unique_ratio > 0.9 and alnum_ratio > 0.8 and (name_hint or avg_len >= 6)


def _is_probably_date(series: pd.Series, col_name: str = "") -> bool:
    values = series.dropna()
    if values.empty:
        return False

    sample = values.astype(str).head(300)
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    success_rate = parsed.notna().mean()
    if success_rate < 0.8:
        return False

    col_hint = any(token in col_name.lower() for token in ["date", "time", "timestamp", "day", "month", "year"])
    delimiter_ratio = sample.str.contains(r"[-/: T]", regex=True).mean()
    digits_only_ratio = sample.str.match(r"^\d+$").mean()

    parsed_non_null = parsed.dropna()
    in_reasonable_range = False
    if not parsed_non_null.empty:
        year_ratio = ((parsed_non_null.dt.year >= 1900) & (parsed_non_null.dt.year <= 2100)).mean()
        in_reasonable_range = bool(year_ratio >= 0.7)

    if digits_only_ratio > 0.9 and not col_hint:
        return False

    return bool(col_hint or delimiter_ratio >= 0.6 or in_reasonable_range)


def _is_text_column(series: pd.Series) -> bool:
    values = series.dropna()
    if values.empty:
        return False

    sample = values.astype(str).head(300)
    avg_len = float(sample.str.len().mean())
    avg_words = float(sample.str.split().str.len().mean())

    return avg_len >= 24 or avg_words >= 4


def detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    column_types: Dict[str, str] = {}

    for col in df.columns:
        series = df[col]

        if is_datetime64_any_dtype(series):
            column_types[col] = "date"
            continue

        if _is_probably_date(series, col):
            column_types[col] = "date"
            continue

        if _looks_identifier(series, col):
            column_types[col] = "id-like"
            continue

        if is_numeric_dtype(series):
            column_types[col] = "numeric"
            continue

        if _is_text_column(series):
            column_types[col] = "text"
            continue

        column_types[col] = "categorical"

    return column_types


def _iqr_outlier_count(series: pd.Series) -> int:
    values = series.dropna().astype(float)
    if values.empty:
        return 0

    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1

    if np.isclose(iqr, 0.0):
        return 0

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return int(((values < lower) | (values > upper)).sum())


def _to_numeric_series(series: pd.Series) -> pd.Series:
    if is_numeric_dtype(series):
        return series.astype(float)
    return pd.to_numeric(series.astype(str), errors="coerce")


def _detect_geospatial_summary(df: pd.DataFrame, column_types: Dict[str, str]) -> Dict[str, Any]:
    lat_col: str | None = None
    lon_col: str | None = None
    lat_score_best = -1.0
    lon_score_best = -1.0

    numeric_candidates: Dict[str, pd.Series] = {}
    for col in df.columns:
        numeric_series = _to_numeric_series(df[col])
        valid_ratio = float(numeric_series.notna().mean())
        if valid_ratio < 0.55:
            continue
        numeric_candidates[col] = numeric_series

    for col, series in numeric_candidates.items():
        name = col.lower()
        lat_hint = any(token in name for token in ["lat", "latitude"])
        lon_hint = any(token in name for token in ["lon", "lng", "longitude"])
        in_lat_ratio = float(series.dropna().between(-90, 90).mean()) if series.notna().any() else 0.0
        in_lon_ratio = float(series.dropna().between(-180, 180).mean()) if series.notna().any() else 0.0

        lat_score = (2.0 if lat_hint else 0.0) + in_lat_ratio
        lon_score = (2.0 if lon_hint else 0.0) + in_lon_ratio

        if lat_score > lat_score_best and in_lat_ratio >= 0.7:
            lat_score_best = lat_score
            lat_col = col
        if lon_score > lon_score_best and in_lon_ratio >= 0.7:
            lon_score_best = lon_score
            lon_col = col

    if lat_col == lon_col:
        lon_col = None
        lon_score_best = -1.0
        for col, series in numeric_candidates.items():
            if col == lat_col:
                continue
            name = col.lower()
            lon_hint = any(token in name for token in ["lon", "lng", "longitude"])
            in_lon_ratio = float(series.dropna().between(-180, 180).mean()) if series.notna().any() else 0.0
            lon_score = (2.0 if lon_hint else 0.0) + in_lon_ratio
            if lon_score > lon_score_best and in_lon_ratio >= 0.7:
                lon_score_best = lon_score
                lon_col = col

    invalid_latitude_values = 0
    invalid_longitude_values = 0
    valid_coordinate_pairs = 0
    invalid_coordinate_pairs = 0
    missing_coordinate_pairs = 0
    bbox: Dict[str, float] = {}

    if lat_col and lon_col:
        lat_series = numeric_candidates[lat_col]
        lon_series = numeric_candidates[lon_col]

        lat_present = lat_series.notna()
        lon_present = lon_series.notna()
        lat_valid = lat_series.between(-90, 90)
        lon_valid = lon_series.between(-180, 180)

        invalid_latitude_values = int((lat_present & ~lat_valid).sum())
        invalid_longitude_values = int((lon_present & ~lon_valid).sum())

        pair_present = lat_present & lon_present
        pair_valid = pair_present & lat_valid & lon_valid
        valid_coordinate_pairs = int(pair_valid.sum())
        invalid_coordinate_pairs = int((pair_present & ~(lat_valid & lon_valid)).sum())
        missing_coordinate_pairs = int((lat_present ^ lon_present).sum())

        if valid_coordinate_pairs > 0:
            valid_lat = lat_series[pair_valid]
            valid_lon = lon_series[pair_valid]
            bbox = {
                "min_lat": round(float(valid_lat.min()), 6),
                "max_lat": round(float(valid_lat.max()), 6),
                "min_lon": round(float(valid_lon.min()), 6),
                "max_lon": round(float(valid_lon.max()), 6),
            }

    geometry_columns: List[str] = []
    invalid_geometry_values: Dict[str, int] = {}
    geom_prefixes = ("POINT", "LINESTRING", "POLYGON", "MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON", "GEOMETRYCOLLECTION")

    for col, col_type in column_types.items():
        if col_type not in {"text", "categorical"}:
            continue
        values = df[col].dropna().astype(str).str.strip()
        if values.empty:
            continue
        sample = values.head(500).str.upper()
        wkt_like = sample.str.startswith(geom_prefixes) & sample.str.contains(r"\(", regex=True)
        ratio = float(wkt_like.mean()) if len(sample) else 0.0
        if ratio >= 0.6:
            geometry_columns.append(col)
            full_upper = values.str.upper()
            full_like = full_upper.str.startswith(geom_prefixes) & full_upper.str.contains(r"\(", regex=True)
            invalid_geometry_values[col] = int((~full_like).sum())

    has_geospatial_data = bool((lat_col and lon_col) or geometry_columns)

    return {
        "has_geospatial_data": has_geospatial_data,
        "latitude_column": lat_col,
        "longitude_column": lon_col,
        "valid_coordinate_pairs": valid_coordinate_pairs,
        "invalid_coordinate_pairs": invalid_coordinate_pairs,
        "missing_coordinate_pairs": missing_coordinate_pairs,
        "invalid_latitude_values": invalid_latitude_values,
        "invalid_longitude_values": invalid_longitude_values,
        "geometry_columns": geometry_columns,
        "invalid_geometry_values": invalid_geometry_values,
        "bbox": bbox,
    }


def profile_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    row_count = int(len(df))
    column_count = int(len(df.columns))
    column_types = detect_column_types(df)

    missing_values: Dict[str, Dict[str, float]] = {}
    constant_columns: List[str] = []
    high_cardinality_columns: List[str] = []
    invalid_dates: Dict[str, int] = {}
    skewed_numeric_columns: Dict[str, float] = {}
    outlier_counts: Dict[str, int] = {}
    type_mismatch_counts: Dict[str, int] = {}
    column_health: List[Dict[str, Any]] = []
    geospatial_summary = _detect_geospatial_summary(df, column_types)
    lat_col = geospatial_summary.get("latitude_column")
    lon_col = geospatial_summary.get("longitude_column")
    geometry_columns = set(geospatial_summary.get("geometry_columns", []))

    for col in df.columns:
        series = df[col]
        missing_count = int(series.isna().sum())
        missing_pct = round((missing_count / row_count) * 100, 2) if row_count else 0.0
        unique_count = int(series.nunique(dropna=True))

        missing_values[col] = {"count": float(missing_count), "pct": float(missing_pct)}

        if unique_count <= 1:
            constant_columns.append(col)

        col_type = column_types[col]
        if col_type in {"categorical", "text"} and unique_count > 50:
            unique_ratio = unique_count / max(row_count, 1)
            if unique_ratio > 0.5:
                high_cardinality_columns.append(col)

        if col_type in {"categorical", "text"}:
            non_null = series.dropna()
            if not non_null.empty:
                casted = pd.to_numeric(non_null.astype(str), errors="coerce")
                numeric_success = casted.notna().mean()
                if 0.2 <= numeric_success < 0.95:
                    type_mismatch_counts[col] = int(casted.isna().sum())

        if col_type == "date":
            if is_datetime64_any_dtype(series):
                invalid_dates[col] = 0
            else:
                parsed = pd.to_datetime(series, errors="coerce", format="mixed")
                invalid_count = int(series.notna().sum() - parsed.notna().sum())
                invalid_dates[col] = invalid_count

        if col_type == "numeric":
            skew = series.dropna().astype(float).skew()
            if pd.notna(skew) and abs(skew) > 1:
                skewed_numeric_columns[col] = round(float(skew), 3)
            outlier_counts[col] = _iqr_outlier_count(series)

        issues: List[str] = []
        if missing_pct > 0:
            issues.append(f"{missing_pct}% missing")
        if col in constant_columns:
            issues.append("constant values")
        if col in high_cardinality_columns:
            issues.append("high cardinality")
        if invalid_dates.get(col, 0) > 0:
            issues.append(f"{invalid_dates[col]} invalid date values")
        if type_mismatch_counts.get(col, 0) > 0:
            issues.append(f"{type_mismatch_counts[col]} type mismatches")
        if col in skewed_numeric_columns:
            issues.append(f"skewed distribution ({skewed_numeric_columns[col]})")
        if outlier_counts.get(col, 0) > 0:
            issues.append(f"{outlier_counts[col]} outliers (IQR)")
        if col == lat_col and geospatial_summary.get("invalid_latitude_values", 0) > 0:
            issues.append(f"{geospatial_summary['invalid_latitude_values']} invalid latitude values")
        if col == lon_col and geospatial_summary.get("invalid_longitude_values", 0) > 0:
            issues.append(f"{geospatial_summary['invalid_longitude_values']} invalid longitude values")
        if col in geometry_columns and geospatial_summary.get("invalid_geometry_values", {}).get(col, 0) > 0:
            issues.append(f"{geospatial_summary['invalid_geometry_values'][col]} invalid geometry values")

        status = "healthy"
        if missing_pct >= 30 or len(issues) >= 3:
            status = "critical"
        elif len(issues) >= 1:
            status = "warning"

        column_health.append(
            {
                "column": col,
                "type": col_type,
                "missing_pct": missing_pct,
                "unique_count": unique_count,
                "status": status,
                "issues": issues,
            }
        )

    return {
        "row_count": row_count,
        "column_count": column_count,
        "column_types": column_types,
        "missing_values": missing_values,
        "duplicate_rows": int(df.duplicated().sum()),
        "constant_columns": constant_columns,
        "high_cardinality_columns": high_cardinality_columns,
        "invalid_dates": invalid_dates,
        "skewed_numeric_columns": skewed_numeric_columns,
        "outlier_counts": outlier_counts,
        "type_mismatch_counts": type_mismatch_counts,
        "geospatial_summary": geospatial_summary,
        "column_health": column_health,
    }
