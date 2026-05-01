from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Tuple

import numpy as np
import pandas as pd

from app.services.anomaly_service import detect_anomalies
from app.services.file_service import validate_filename
from app.services.profile_service import profile_dataset
from app.services.recommendation_service import generate_auto_fix_plan, generate_recommendations

TB_MODE_TRIGGER_MB = int(os.getenv("ANOMIRA_TB_MODE_TRIGGER_MB", "512"))
TB_MODE_TRIGGER_BYTES = TB_MODE_TRIGGER_MB * 1024 * 1024 if TB_MODE_TRIGGER_MB > 0 else 0
CHUNK_ROWS = max(5000, int(os.getenv("ANOMIRA_CHUNK_ROWS", "50000")))
MAX_SAMPLE_ROWS = max(20000, int(os.getenv("ANOMIRA_LARGE_SAMPLE_ROWS", "120000")))
PROGRESS_UPDATE_EVERY_CHUNKS = max(1, int(os.getenv("ANOMIRA_PROGRESS_UPDATE_EVERY_CHUNKS", "3")))
SAMPLE_SEED = int(os.getenv("ANOMIRA_SAMPLE_SEED", "42"))

CHUNKABLE_SUFFIXES = {".csv", ".tsv", ".txt", ".jsonl"}
SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".json", ".jsonl"}


class LargeAnalysisError(Exception):
    pass


def should_use_chunked_mode(file_path: str | Path, filename: str) -> bool:
    _, suffix = validate_filename(filename)
    if suffix not in CHUNKABLE_SUFFIXES:
        return False
    if TB_MODE_TRIGGER_BYTES <= 0:
        return True
    try:
        size = Path(file_path).stat().st_size
    except OSError:
        return False
    return size >= TB_MODE_TRIGGER_BYTES


def _chunk_reader(path: str | Path, suffix: str) -> Iterator[pd.DataFrame]:
    file_path = str(path)
    if suffix == ".csv":
        return pd.read_csv(file_path, low_memory=False, chunksize=CHUNK_ROWS)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(file_path, sep="\t", low_memory=False, chunksize=CHUNK_ROWS)
    if suffix == ".jsonl":
        return pd.read_json(file_path, lines=True, chunksize=CHUNK_ROWS)
    raise LargeAnalysisError(f"Chunked mode is not supported for '{suffix}'. Use csv/tsv/txt/jsonl.")


def _update_sample(
    sample_df: pd.DataFrame | None,
    chunk: pd.DataFrame,
    seen_rows_before: int,
    chunk_index: int,
) -> pd.DataFrame:
    if chunk.empty:
        return sample_df if sample_df is not None else pd.DataFrame()

    chunk_copy = chunk.copy()
    if sample_df is None or sample_df.empty:
        if len(chunk_copy) <= MAX_SAMPLE_ROWS:
            return chunk_copy.reset_index(drop=True)
        return chunk_copy.sample(n=MAX_SAMPLE_ROWS, random_state=SAMPLE_SEED).reset_index(drop=True)

    if len(sample_df) < MAX_SAMPLE_ROWS:
        remaining = MAX_SAMPLE_ROWS - len(sample_df)
        if len(chunk_copy) <= remaining:
            return pd.concat([sample_df, chunk_copy], ignore_index=True)
        sampled = chunk_copy.sample(n=remaining, random_state=SAMPLE_SEED + chunk_index)
        return pd.concat([sample_df, sampled], ignore_index=True)

    current_total = seen_rows_before + len(chunk_copy)
    if current_total <= 0:
        return sample_df

    keep_ratio = MAX_SAMPLE_ROWS / float(current_total)
    candidate_rows = int(max(1, round(len(chunk_copy) * keep_ratio)))
    candidate_rows = min(candidate_rows, len(chunk_copy))
    candidate = chunk_copy.sample(n=candidate_rows, random_state=SAMPLE_SEED + chunk_index)
    merged = pd.concat([sample_df, candidate], ignore_index=True)
    if len(merged) <= MAX_SAMPLE_ROWS:
        return merged.reset_index(drop=True)
    return merged.sample(n=MAX_SAMPLE_ROWS, random_state=SAMPLE_SEED + (chunk_index * 13)).reset_index(drop=True)


def _scale_count(sample_count: int, sample_size: int, full_size: int) -> int:
    if sample_size <= 0:
        return int(sample_count)
    if full_size <= sample_size:
        return int(sample_count)
    return int(round((sample_count / float(sample_size)) * full_size))


def _build_scaled_quality_anomalies(
    sample_quality: Dict[str, Any],
    profile: Dict[str, Any],
    sample_size: int,
    full_size: int,
) -> Dict[str, Any]:
    quality = dict(sample_quality)
    for issue in ["duplicates", "impossible_values", "inconsistent_categories"]:
        payload = dict(quality.get(issue, {}))
        payload["count"] = _scale_count(int(payload.get("count", 0)), sample_size, full_size)
        quality[issue] = payload

    missing_count = int(sum(float(item.get("count", 0.0)) for item in profile.get("missing_values", {}).values()))
    missing_columns = [col for col, item in profile.get("missing_values", {}).items() if float(item.get("count", 0.0)) > 0]
    quality["missing_values"] = {"count": missing_count, "columns": missing_columns}
    quality["invalid_dates"] = {
        "count": int(sum(int(v) for v in profile.get("invalid_dates", {}).values())),
        "columns": [col for col, count in profile.get("invalid_dates", {}).items() if int(count) > 0],
    }

    geo_summary = profile.get("geospatial_summary", {})
    geo_count = int(
        geo_summary.get("invalid_coordinate_pairs", 0)
        + geo_summary.get("missing_coordinate_pairs", 0)
        + geo_summary.get("invalid_latitude_values", 0)
        + geo_summary.get("invalid_longitude_values", 0)
    )
    geo_columns = [col for col in [geo_summary.get("latitude_column"), geo_summary.get("longitude_column")] if col]
    quality["invalid_geo_coordinates"] = {"count": geo_count, "columns": geo_columns}
    quality["extreme_skew"] = {
        "count": int(len(profile.get("skewed_numeric_columns", {}))),
        "columns": list(profile.get("skewed_numeric_columns", {}).keys()),
    }
    return quality


def analyze_large_dataset_from_path(
    file_path: str | Path,
    filename: str,
    *,
    top_n: int,
    expected_columns: List[str] | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str], List[Dict[str, Any]], Dict[str, Any]]:
    _, suffix = validate_filename(filename)
    if suffix not in SUPPORTED_SUFFIXES:
        raise LargeAnalysisError(f"Unsupported file format: {suffix}")
    if suffix not in CHUNKABLE_SUFFIXES:
        raise LargeAnalysisError(
            f"TB-ready chunked mode currently supports csv/tsv/txt/jsonl only. Received: {suffix}"
        )

    if progress_callback:
        progress_callback(35.0, "Profiling large dataset in chunked mode.")

    row_count = 0
    columns: List[str] = []
    missing_counts: Dict[str, int] = {}
    sample_df: pd.DataFrame | None = None
    chunk_index = 0
    rows_seen_for_sampling = 0

    for chunk in _chunk_reader(file_path, suffix):
        chunk_index += 1
        if chunk.empty:
            continue

        chunk.columns = [str(col).strip() for col in chunk.columns]
        if not columns:
            columns = [str(col) for col in chunk.columns]
            missing_counts = {col: 0 for col in columns}

        for col in chunk.columns:
            if col not in missing_counts:
                missing_counts[col] = 0
                columns.append(col)
        for col in columns:
            if col not in chunk.columns:
                chunk[col] = np.nan
        chunk = chunk[columns]

        chunk_rows = int(len(chunk))
        row_count += chunk_rows
        rows_seen_for_sampling += chunk_rows

        chunk_missing = chunk.isna().sum()
        for col in columns:
            missing_counts[col] += int(chunk_missing.get(col, 0))

        sample_df = _update_sample(sample_df, chunk, rows_seen_for_sampling - chunk_rows, chunk_index)

        if progress_callback and (chunk_index % PROGRESS_UPDATE_EVERY_CHUNKS == 0):
            progress = min(58.0, 35.0 + (chunk_index * 1.4))
            progress_callback(progress, f"Scanned {row_count:,} rows in chunked mode.")

    if row_count <= 0 or sample_df is None or sample_df.empty:
        raise LargeAnalysisError("Dataset contains no rows after chunked scan.")

    sample_df = sample_df.reset_index(drop=True)
    sample_profile = profile_dataset(sample_df)

    if progress_callback:
        progress_callback(62.0, "Building profile and anomaly model from representative sample.")

    missing_values = {
        col: {
            "count": float(missing_counts.get(col, 0)),
            "pct": round((missing_counts.get(col, 0) / row_count) * 100.0, 2) if row_count else 0.0,
        }
        for col in columns
    }

    scale_ratio = row_count / max(len(sample_df), 1)
    scaled_outliers = {
        col: int(round(float(count) * scale_ratio))
        for col, count in sample_profile.get("outlier_counts", {}).items()
    }

    duplicate_rows_estimate = _scale_count(
        int(sample_profile.get("duplicate_rows", 0)),
        int(len(sample_df)),
        int(row_count),
    )

    column_health_map = {item["column"]: dict(item) for item in sample_profile.get("column_health", [])}
    column_health: List[Dict[str, Any]] = []
    for col in columns:
        base = column_health_map.get(
            col,
            {
                "column": col,
                "type": sample_profile.get("column_types", {}).get(col, "categorical"),
                "missing_pct": 0.0,
                "unique_count": 0,
                "status": "healthy",
                "issues": [],
            },
        )
        base["missing_pct"] = missing_values[col]["pct"]
        column_health.append(base)

    profile = {
        **sample_profile,
        "row_count": int(row_count),
        "column_count": int(len(columns)),
        "missing_values": missing_values,
        "duplicate_rows": int(duplicate_rows_estimate),
        "outlier_counts": scaled_outliers,
        "column_health": column_health,
    }

    sample_anomalies = detect_anomalies(
        sample_df,
        profile["column_types"],
        profile=profile,
        top_n=top_n,
    )
    sample_anomalies.pop("_all_scores", None)

    sample_size = int(len(sample_df))
    suspicious_estimate = _scale_count(
        int(sample_anomalies.get("suspicious_count", 0)),
        sample_size,
        int(row_count),
    )
    scaled_severity = {
        key: _scale_count(int(value), sample_size, int(row_count))
        for key, value in sample_anomalies.get("severity_breakdown", {}).items()
    }
    scaled_types = {
        key: _scale_count(int(value), sample_size, int(row_count))
        for key, value in sample_anomalies.get("anomaly_type_breakdown", {}).items()
    }
    scaled_categories = {
        key: _scale_count(int(value), sample_size, int(row_count))
        for key, value in sample_anomalies.get("anomaly_category_breakdown", {}).items()
    }

    quality_scaled = _build_scaled_quality_anomalies(
        sample_anomalies.get("quality_anomalies", {}),
        profile,
        sample_size,
        int(row_count),
    )
    quality_total_scaled = int(sum(int(payload.get("count", 0)) for payload in quality_scaled.values()))
    if scaled_categories:
        scaled_categories["data_quality"] = quality_total_scaled

    scaled_groups = []
    for group in sample_anomalies.get("anomaly_groups", []):
        group_copy = dict(group)
        category_key = str(group_copy.get("category_key", ""))
        if category_key == "data_quality":
            group_copy["count"] = quality_total_scaled
        else:
            group_copy["count"] = _scale_count(int(group_copy.get("count", 0)), sample_size, int(row_count))
            scaled_group_severity = {}
            for sev, sev_count in dict(group_copy.get("severity_breakdown", {})).items():
                scaled_group_severity[sev] = _scale_count(int(sev_count), sample_size, int(row_count))
            group_copy["severity_breakdown"] = scaled_group_severity
        scaled_groups.append(group_copy)

    anomalies = {
        **sample_anomalies,
        "total_rows": int(row_count),
        "suspicious_count": int(suspicious_estimate),
        "severity_breakdown": scaled_severity,
        "anomaly_type_breakdown": scaled_types,
        "anomaly_category_breakdown": scaled_categories,
        "anomaly_groups": scaled_groups,
        "quality_anomalies": quality_scaled,
        "analysis_metadata": {
            "analysis_mode": "chunked_sampled",
            "approximate": True,
            "sampled_rows": sample_size,
            "sampled_ratio": round(sample_size / float(row_count), 6),
        },
    }

    recommendations = generate_recommendations(profile, anomalies, expected_columns=expected_columns)
    auto_fix_plan = generate_auto_fix_plan(profile, anomalies, expected_columns=expected_columns)

    metadata = {
        "analysis_mode": "chunked_sampled",
        "approximate": True,
        "sampled_rows": sample_size,
        "sampled_ratio": round(sample_size / float(row_count), 6),
        "chunk_rows": CHUNK_ROWS,
    }

    if progress_callback:
        progress_callback(82.0, "Finalizing recommendations and action plan.")

    return profile, anomalies, recommendations, auto_fix_plan, metadata
