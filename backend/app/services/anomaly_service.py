from __future__ import annotations

import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

from app.utils.serialization import to_serializable

# Avoid expensive core discovery fallbacks (e.g. missing wmic in some environments).
CPU_COUNT = max(1, int(os.cpu_count() or 1))
MODEL_JOBS = int(os.getenv("ANOMIRA_MODEL_JOBS", "1"))
if MODEL_JOBS == 0:
    MODEL_JOBS = 1
os.environ["LOKY_MAX_CPU_COUNT"] = str(CPU_COUNT)

LARGE_DATASET_ROW_THRESHOLD = 120000
MAX_TRAIN_ROWS = 100000
MAX_CONTEXT_COLUMNS = 4
MAX_CONTEXT_NUMERIC_COLUMNS = 12
MAX_TIME_SERIES_COLUMNS = 8
MAX_TIME_EVENTS = 600

ANOMALY_TYPE_LABELS = {
    "point_anomaly_global_outlier": "point anomaly / global outlier",
    "contextual_anomaly": "contextual anomaly",
    "collective_anomaly": "collective anomaly",
    "time_series_spike": "time-series spike",
    "time_series_dip": "time-series dip",
    "time_series_trend_change": "time-series trend change",
    "time_series_seasonal_break": "time-series seasonal break",
    "high_dimensional_multivariate_anomaly": "high-dimensional multivariate anomaly",
    "geospatial_anomaly": "geospatial anomaly",
}

ANOMALY_CATEGORY_META = {
    "point_global": {
        "label": "Point / Global Outliers",
        "description": "Individual rows far from normal numeric ranges or global distribution.",
        "count_label": "records",
    },
    "contextual": {
        "label": "Contextual Anomalies",
        "description": "Rows unusual inside their category or segment context.",
        "count_label": "records",
    },
    "collective": {
        "label": "Collective Anomalies",
        "description": "Consecutive groups of records that are abnormal together.",
        "count_label": "records",
    },
    "time_series": {
        "label": "Time-Series Anomalies",
        "description": "Spikes, dips, trend changes, or seasonal breaks over time.",
        "count_label": "records",
    },
    "multivariate": {
        "label": "High-Dimensional / Multivariate",
        "description": "Rows with unusual cross-feature combinations.",
        "count_label": "records",
    },
    "geospatial": {
        "label": "Geospatial Anomalies",
        "description": "Location points far from expected geographic patterns.",
        "count_label": "records",
    },
    "data_quality": {
        "label": "Data Quality Anomalies",
        "description": "Missing values, duplicates, impossible values, inconsistent categories, skew, invalid dates, and invalid coordinates.",
        "count_label": "quality events",
    },
}

ANOMALY_CATEGORY_PRIORITY = [
    "time_series",
    "collective",
    "contextual",
    "multivariate",
    "geospatial",
    "point_global",
]

TIME_SERIES_TYPE_DEFINITIONS = {
    "time_series_spike": "A sudden upward jump where the value rises above its local rolling baseline by more than a robust threshold.",
    "time_series_dip": "A sudden downward drop where the value falls below its local rolling baseline by more than a robust threshold.",
    "time_series_trend_change": "An abrupt slope change where the point-to-point change deviates strongly from the recent local trend pattern.",
    "time_series_seasonal_break": "A break in repeating seasonal behavior where the value diverges from its lag-based seasonal expectation.",
}


def _format_metric(value: float | int | np.floating | np.integer) -> str:
    numeric = float(value)
    if np.isnan(numeric) or np.isinf(numeric):
        return "n/a"
    if abs(numeric) >= 1000:
        return f"{numeric:,.1f}"
    if abs(numeric) >= 100:
        return f"{numeric:.2f}"
    if abs(numeric) >= 1:
        return f"{numeric:.3f}"
    return f"{numeric:.4f}"


def _optional_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if np.isnan(numeric) or np.isinf(numeric):
        return None

    return round(numeric, 6)


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    num = _optional_float(numerator)
    den = _optional_float(denominator)
    if num is None or den is None or np.isclose(den, 0.0):
        return None
    return round(num / den, 6)


def _safe_pct_delta(current: Any, reference: Any) -> float | None:
    cur = _optional_float(current)
    ref = _optional_float(reference)
    if cur is None or ref is None or np.isclose(ref, 0.0):
        return None
    return round(((cur - ref) / abs(ref)) * 100.0, 6)


def _format_percent(value: float | None) -> str:
    if value is None or np.isnan(value) or np.isinf(value):
        return "n/a"
    return f"{value:.2f}%"


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype(float)
    min_v = float(np.min(values))
    max_v = float(np.max(values))

    if np.isclose(min_v, max_v):
        return np.zeros_like(values)

    return (values - min_v) / (max_v - min_v)


def _severity(score: float) -> str:
    if score >= 0.8:
        return "critical"
    if score >= 0.6:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _type_to_category(anomaly_type: str) -> str:
    if anomaly_type.startswith("time_series_"):
        return "time_series"
    if anomaly_type == "point_anomaly_global_outlier":
        return "point_global"
    if anomaly_type == "contextual_anomaly":
        return "contextual"
    if anomaly_type == "collective_anomaly":
        return "collective"
    if anomaly_type == "high_dimensional_multivariate_anomaly":
        return "multivariate"
    if anomaly_type == "geospatial_anomaly":
        return "geospatial"
    return "point_global"


def _primary_category(categories: List[str]) -> str:
    if not categories:
        return "point_global"
    for category in ANOMALY_CATEGORY_PRIORITY:
        if category in categories:
            return category
    return categories[0]


def _build_anomaly_groups(
    suspicious_records: List[Dict[str, Any]],
    quality_anomalies: Dict[str, Any],
    *,
    sample_limit: int = 8,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for key, meta in ANOMALY_CATEGORY_META.items():
        grouped[key] = {
            "category_key": key,
            "category_label": meta["label"],
            "description": meta["description"],
            "count_label": meta["count_label"],
            "count": 0,
            "severity_breakdown": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "top_affected_columns": [],
            "anomaly_signals": [],
            "sample_records": [],
        }
        grouped[key]["_column_counter"] = Counter()
        grouped[key]["_signal_counter"] = Counter()

    for record in suspicious_records:
        categories = list(dict.fromkeys(record.get("anomaly_categories", [])))
        if not categories:
            continue

        primary = record.get("primary_category") or _primary_category(categories)
        group = grouped.get(primary)
        if group is None:
            continue

        group["count"] += 1
        severity = record.get("severity", "low")
        if severity not in group["severity_breakdown"]:
            group["severity_breakdown"][severity] = 0
        group["severity_breakdown"][severity] += 1

        group["_column_counter"].update(record.get("affected_columns", []))
        group["_signal_counter"].update(record.get("anomaly_types", []))

        if len(group["sample_records"]) < sample_limit:
            group["sample_records"].append(
                {
                    "row_index": int(record.get("row_index", -1)),
                    "anomaly_score": float(record.get("anomaly_score", 0.0)),
                    "severity": str(record.get("severity", "low")),
                    "anomaly_types": record.get("anomaly_types", []),
                    "affected_columns": record.get("affected_columns", []),
                    "explanation": str(record.get("explanation", "")),
                }
            )

    quality_group = grouped["data_quality"]
    quality_count = int(sum(int(payload.get("count", 0)) for payload in quality_anomalies.values()))
    quality_group["count"] = quality_count
    for issue, payload in quality_anomalies.items():
        issue_count = int(payload.get("count", 0))
        if issue_count > 0:
            quality_group["_signal_counter"][issue] += issue_count
            quality_group["_column_counter"].update(payload.get("columns", []))

    ordered = [
        "point_global",
        "contextual",
        "collective",
        "time_series",
        "multivariate",
        "geospatial",
        "data_quality",
    ]

    result: List[Dict[str, Any]] = []
    for key in ordered:
        group = grouped[key]
        group["top_affected_columns"] = [
            {"column": column, "count": int(count)}
            for column, count in group["_column_counter"].most_common(6)
        ]
        group["anomaly_signals"] = [
            {
                "signal": signal,
                "label": ANOMALY_TYPE_LABELS.get(signal, signal.replace("_", " ")),
                "count": int(count),
            }
            for signal, count in group["_signal_counter"].most_common(6)
        ]
        group.pop("_column_counter", None)
        group.pop("_signal_counter", None)
        if int(group["count"]) > 0:
            result.append(group)

    return result


def _detect_best_time_column(df: pd.DataFrame, column_types: Dict[str, str]) -> Tuple[str | None, pd.Series | None]:
    date_columns = [col for col, col_type in column_types.items() if col_type == "date"]
    best_col: str | None = None
    best_series: pd.Series | None = None
    best_score = 0.0

    for col in date_columns:
        parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
        score = float(parsed.notna().mean())
        if score > best_score and parsed.notna().sum() >= 8:
            best_score = score
            best_col = col
            best_series = parsed

    return best_col, best_series


def _robust_threshold(series: pd.Series, window: int) -> np.ndarray:
    rolling_median = series.rolling(window=window, center=True, min_periods=max(3, window // 2)).median()
    residual = (series - rolling_median).abs()
    mad = residual.rolling(window=window, center=True, min_periods=max(3, window // 2)).median()
    fallback = np.nanstd(series.to_numpy(dtype=float)) * 1.5
    threshold = np.maximum((mad * 6).fillna(0.0).to_numpy(), fallback)
    return threshold


def _detect_contextual_anomalies(
    df: pd.DataFrame,
    feature_df: pd.DataFrame,
    numeric_columns: List[str],
    column_types: Dict[str, str],
) -> Tuple[np.ndarray, Dict[int, List[str]], Dict[int, set[str]]]:
    row_count = len(df)
    flags = np.zeros(row_count, dtype=bool)
    context_details: Dict[int, List[str]] = defaultdict(list)
    affected: Dict[int, set[str]] = defaultdict(set)

    context_columns = [
        col
        for col, col_type in column_types.items()
        if col_type == "categorical" and 1 < int(df[col].nunique(dropna=True)) <= 30
    ]

    if not context_columns or not numeric_columns:
        return flags, context_details, affected

    for context_col in context_columns[:MAX_CONTEXT_COLUMNS]:
        ctx_series = df[context_col].astype(str).fillna("__MISSING__")
        group_counts = ctx_series.value_counts(dropna=False)
        valid_groups = set(group_counts[group_counts >= 8].index.tolist())
        if len(valid_groups) < 2:
            continue
        valid_mask = ctx_series.isin(valid_groups)

        for num_col in numeric_columns[:MAX_CONTEXT_NUMERIC_COLUMNS]:
            values = feature_df[num_col]
            frame = pd.DataFrame({"ctx": ctx_series, "value": values})
            group_mean = frame.groupby("ctx")["value"].transform("mean")
            group_std = frame.groupby("ctx")["value"].transform("std").replace(0, np.nan)
            z = ((values - group_mean).abs() / group_std).fillna(0.0)
            mask = (z > 3.2) & valid_mask
            idxs = np.where(mask.to_numpy())[0]
            if len(idxs) == 0:
                continue

            flags[idxs] = True
            for idx in idxs[:20000]:
                if len(context_details[idx]) < 2:
                    context_value = ctx_series.iloc[idx]
                    context_details[idx].append(f"{context_col}={context_value} ({num_col} z={float(z.iloc[idx]):.2f})")
                affected[idx].add(num_col)

    return flags, context_details, affected


def _detect_time_series_anomalies(
    feature_df: pd.DataFrame,
    sorted_indices: np.ndarray,
    time_values_sorted: pd.Series,
    numeric_columns: List[str],
) -> Tuple[Dict[str, np.ndarray], List[Dict[str, Any]], Dict[int, set[str]], Dict[int, List[str]]]:
    row_count = len(feature_df)
    flags = {
        "time_series_spike": np.zeros(row_count, dtype=bool),
        "time_series_dip": np.zeros(row_count, dtype=bool),
        "time_series_trend_change": np.zeros(row_count, dtype=bool),
        "time_series_seasonal_break": np.zeros(row_count, dtype=bool),
    }
    events: List[Dict[str, Any]] = []
    affected: Dict[int, set[str]] = defaultdict(set)
    details: Dict[int, List[str]] = defaultdict(list)

    if len(sorted_indices) < 12:
        return flags, events, affected, details

    if len(time_values_sorted) != len(sorted_indices):
        return flags, events, affected, details

    window = int(min(31, max(7, len(sorted_indices) // 40)))

    for col in numeric_columns[:MAX_TIME_SERIES_COLUMNS]:
        series_sorted = feature_df.iloc[sorted_indices][col].astype(float)
        series_values = series_sorted.to_numpy()

        threshold = _robust_threshold(series_sorted, window)
        rolling_median = series_sorted.rolling(window=window, center=True, min_periods=max(3, window // 2)).median()
        residual = series_values - rolling_median.to_numpy()

        spike_pos = np.where(residual > threshold)[0]
        dip_pos = np.where(residual < -threshold)[0]

        diff = np.diff(series_values, prepend=series_values[0])
        diff_series = pd.Series(diff)
        diff_median = diff_series.rolling(window=window, center=True, min_periods=max(3, window // 2)).median()
        diff_residual = (diff_series - diff_median).abs()
        diff_mad = diff_residual.rolling(window=window, center=True, min_periods=max(3, window // 2)).median()
        diff_threshold = np.maximum((diff_mad * 6).fillna(0.0).to_numpy(), np.nanstd(diff) * 2.0)
        trend_pos = np.where(diff_residual.to_numpy() > diff_threshold)[0]
        trend_pos = trend_pos[trend_pos > max(2, window // 3)]

        seasonal_pos = np.array([], dtype=int)
        best_lag = None
        best_corr = 0.0
        for lag in [7, 12, 24, 30]:
            if len(series_values) < lag * 3:
                continue
            a = series_values[lag:]
            b = series_values[:-lag]
            if np.isclose(np.nanstd(a), 0.0) or np.isclose(np.nanstd(b), 0.0):
                continue
            corr = np.corrcoef(a, b)[0, 1]
            if np.isnan(corr):
                continue
            if abs(float(corr)) > best_corr:
                best_corr = abs(float(corr))
                best_lag = lag

        if best_lag is not None and best_corr >= 0.25:
            shifted = np.roll(series_values, best_lag)
            mask = np.zeros(len(series_values), dtype=bool)
            mask[best_lag:] = True
            seasonal_resid = np.abs(series_values - shifted)
            base = seasonal_resid[mask]
            med = float(np.nanmedian(base)) if base.size else 0.0
            mad = float(np.nanmedian(np.abs(base - med))) if base.size else 0.0
            threshold_seasonal = max(med + 6 * mad, float(np.nanstd(base) * 2.5))
            seasonal_pos = np.where((seasonal_resid > threshold_seasonal) & mask)[0]

        type_positions = {
            "time_series_spike": spike_pos,
            "time_series_dip": dip_pos,
            "time_series_trend_change": trend_pos,
            "time_series_seasonal_break": seasonal_pos,
        }

        for anomaly_type, positions in type_positions.items():
            if len(positions) == 0:
                continue
            original_rows = sorted_indices[positions]
            flags[anomaly_type][original_rows] = True

            for pos in positions[:120]:
                row_idx = int(sorted_indices[pos])
                timestamp = time_values_sorted.iloc[pos]
                timestamp_value = timestamp.isoformat() if pd.notna(timestamp) else None
                prev_pos = pos - 1 if pos > 0 else None
                prev_value = _optional_float(series_values[prev_pos]) if prev_pos is not None else None
                prev_timestamp = (
                    time_values_sorted.iloc[prev_pos].isoformat()
                    if prev_pos is not None and pd.notna(time_values_sorted.iloc[prev_pos])
                    else None
                )

                current_value = _optional_float(series_values[pos])
                baseline_value = _optional_float(rolling_median.iloc[pos])
                deviation_value = _optional_float(residual[pos])
                threshold_value = _optional_float(threshold[pos])
                deviation_ratio = _safe_ratio(abs(residual[pos]), threshold[pos])
                baseline_pct_delta = _safe_pct_delta(series_values[pos], rolling_median.iloc[pos])
                prev_step_delta = (
                    _optional_float(series_values[pos] - series_values[prev_pos])
                    if prev_pos is not None
                    else None
                )
                prev_step_pct = (
                    _safe_pct_delta(series_values[pos], series_values[prev_pos])
                    if prev_pos is not None
                    else None
                )
                what_happened = f"{anomaly_type.replace('_', ' ')} detected in {col}."
                evidence = ""
                metrics: Dict[str, Any] = {}

                if anomaly_type == "time_series_spike":
                    what_happened = (
                        f"{col} spiked: value={_format_metric(series_values[pos])} vs local baseline={_format_metric(rolling_median.iloc[pos])} "
                        f"({ _format_percent(baseline_pct_delta) } from baseline). Residual={_format_metric(residual[pos])} exceeded threshold={_format_metric(threshold[pos])} "
                        f"(strength={_format_metric(deviation_ratio) if deviation_ratio is not None else 'n/a'}x)."
                    )
                    evidence = (
                        f"current={_format_metric(series_values[pos])}, baseline={_format_metric(rolling_median.iloc[pos])}, "
                        f"residual={_format_metric(residual[pos])}, threshold={_format_metric(threshold[pos])}, "
                        f"ratio={_format_metric(deviation_ratio) if deviation_ratio is not None else 'n/a'}x"
                    )
                    metrics = {
                        "direction": "up",
                        "window": window,
                        "current_value": current_value,
                        "local_baseline": baseline_value,
                        "deviation": deviation_value,
                        "threshold": threshold_value,
                        "threshold_ratio": _optional_float(deviation_ratio),
                        "pct_from_baseline": _optional_float(baseline_pct_delta),
                        "prev_value": prev_value,
                        "prev_timestamp": prev_timestamp,
                        "delta_from_prev": prev_step_delta,
                        "pct_from_prev": _optional_float(prev_step_pct),
                    }
                elif anomaly_type == "time_series_dip":
                    what_happened = (
                        f"{col} dipped: value={_format_metric(series_values[pos])} vs local baseline={_format_metric(rolling_median.iloc[pos])} "
                        f"({ _format_percent(baseline_pct_delta) } from baseline). Residual={_format_metric(residual[pos])} dropped below -threshold={_format_metric(threshold[pos])} "
                        f"(strength={_format_metric(deviation_ratio) if deviation_ratio is not None else 'n/a'}x)."
                    )
                    evidence = (
                        f"current={_format_metric(series_values[pos])}, baseline={_format_metric(rolling_median.iloc[pos])}, "
                        f"residual={_format_metric(residual[pos])}, threshold={_format_metric(threshold[pos])}, "
                        f"ratio={_format_metric(deviation_ratio) if deviation_ratio is not None else 'n/a'}x"
                    )
                    metrics = {
                        "direction": "down",
                        "window": window,
                        "current_value": current_value,
                        "local_baseline": baseline_value,
                        "deviation": deviation_value,
                        "threshold": threshold_value,
                        "threshold_ratio": _optional_float(deviation_ratio),
                        "pct_from_baseline": _optional_float(baseline_pct_delta),
                        "prev_value": prev_value,
                        "prev_timestamp": prev_timestamp,
                        "delta_from_prev": prev_step_delta,
                        "pct_from_prev": _optional_float(prev_step_pct),
                    }
                elif anomaly_type == "time_series_trend_change":
                    local_diff = _optional_float(diff_median.iloc[pos])
                    diff_value = _optional_float(diff[pos])
                    diff_dev = _optional_float(diff_residual.iloc[pos])
                    diff_thresh = _optional_float(diff_threshold[pos])
                    diff_ratio = _safe_ratio(diff_residual.iloc[pos], diff_threshold[pos])
                    what_happened = (
                        f"{col} trend changed: step change={_format_metric(diff[pos])} vs local step baseline={_format_metric(diff_median.iloc[pos])}. "
                        f"Diff deviation={_format_metric(diff_residual.iloc[pos])} exceeded threshold={_format_metric(diff_threshold[pos])} "
                        f"(strength={_format_metric(diff_ratio) if diff_ratio is not None else 'n/a'}x)."
                    )
                    evidence = (
                        f"step={_format_metric(diff[pos])}, local_step={_format_metric(diff_median.iloc[pos])}, "
                        f"deviation={_format_metric(diff_residual.iloc[pos])}, threshold={_format_metric(diff_threshold[pos])}, "
                        f"ratio={_format_metric(diff_ratio) if diff_ratio is not None else 'n/a'}x"
                    )
                    metrics = {
                        "window": window,
                        "current_value": current_value,
                        "current_diff": diff_value,
                        "local_diff_baseline": local_diff,
                        "diff_deviation": diff_dev,
                        "threshold": diff_thresh,
                        "threshold_ratio": _optional_float(diff_ratio),
                        "prev_value": prev_value,
                        "prev_timestamp": prev_timestamp,
                        "delta_from_prev": prev_step_delta,
                        "pct_from_prev": _optional_float(prev_step_pct),
                    }
                elif anomaly_type == "time_series_seasonal_break":
                    seasonal_delta = _optional_float(seasonal_resid[pos])
                    seasonal_thresh = _optional_float(threshold_seasonal)
                    expected_value = _optional_float(shifted[pos])
                    seasonal_ratio = _safe_ratio(seasonal_resid[pos], threshold_seasonal)
                    seasonal_pct_error = _safe_pct_delta(series_values[pos], shifted[pos])
                    what_happened = (
                        f"{col} seasonal break: value={_format_metric(series_values[pos])} vs seasonal expected={_format_metric(shifted[pos])} "
                        f"({ _format_percent(seasonal_pct_error) } error). Seasonal residual={_format_metric(seasonal_resid[pos])} exceeded threshold={_format_metric(threshold_seasonal)} "
                        f"(strength={_format_metric(seasonal_ratio) if seasonal_ratio is not None else 'n/a'}x, lag={best_lag})."
                    )
                    evidence = (
                        f"current={_format_metric(series_values[pos])}, expected={_format_metric(shifted[pos])}, "
                        f"residual={_format_metric(seasonal_resid[pos])}, threshold={_format_metric(threshold_seasonal)}, "
                        f"ratio={_format_metric(seasonal_ratio) if seasonal_ratio is not None else 'n/a'}x, lag={best_lag}, corr={_format_metric(best_corr)}"
                    )
                    metrics = {
                        "window": window,
                        "current_value": current_value,
                        "seasonal_expected": expected_value,
                        "seasonal_residual": seasonal_delta,
                        "threshold": seasonal_thresh,
                        "threshold_ratio": _optional_float(seasonal_ratio),
                        "pct_error_vs_expected": _optional_float(seasonal_pct_error),
                        "lag": int(best_lag) if best_lag is not None else None,
                        "seasonality_correlation": _optional_float(best_corr),
                        "prev_value": prev_value,
                        "prev_timestamp": prev_timestamp,
                        "delta_from_prev": prev_step_delta,
                        "pct_from_prev": _optional_float(prev_step_pct),
                    }

                event = {
                    "anomaly_type": anomaly_type,
                    "type_label": ANOMALY_TYPE_LABELS.get(anomaly_type, anomaly_type.replace("_", " ")),
                    "definition": TIME_SERIES_TYPE_DEFINITIONS.get(anomaly_type, ""),
                    "what_happened": what_happened,
                    "evidence": evidence,
                    "row_index": row_idx,
                    "column": col,
                    "timestamp": timestamp_value,
                    "metrics": metrics,
                }
                if len(events) < MAX_TIME_EVENTS:
                    events.append(event)
                affected[row_idx].add(col)
                if len(details[row_idx]) < 2:
                    details[row_idx].append(what_happened)

    return flags, events, affected, details


def _detect_collective_anomalies(
    anomaly_scores: np.ndarray,
    sorted_indices: np.ndarray,
    sorted_times: pd.Series | None,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    row_count = len(anomaly_scores)
    flags = np.zeros(row_count, dtype=bool)
    segments: List[Dict[str, Any]] = []

    ordered_scores = anomaly_scores[sorted_indices]
    if len(ordered_scores) < 6:
        return flags, segments

    threshold = max(0.58, float(np.quantile(ordered_scores, 0.9)))
    high_mask = ordered_scores >= threshold

    start = None
    for idx, is_high in enumerate(high_mask):
        if is_high and start is None:
            start = idx
        elif not is_high and start is not None:
            length = idx - start
            if length >= 3:
                segment_rows = sorted_indices[start:idx]
                flags[segment_rows] = True
                peak = float(np.max(anomaly_scores[segment_rows]))
                segment_info = {
                    "start_row_index": int(segment_rows[0]),
                    "end_row_index": int(segment_rows[-1]),
                    "length": int(length),
                    "peak_score": round(peak, 4),
                }
                if sorted_times is not None and len(sorted_times) > idx:
                    start_time = sorted_times.iloc[start]
                    end_time = sorted_times.iloc[idx - 1]
                    segment_info["start_time"] = start_time.isoformat() if pd.notna(start_time) else None
                    segment_info["end_time"] = end_time.isoformat() if pd.notna(end_time) else None
                segments.append(segment_info)
            start = None

    if start is not None:
        length = len(high_mask) - start
        if length >= 3:
            segment_rows = sorted_indices[start:]
            flags[segment_rows] = True
            peak = float(np.max(anomaly_scores[segment_rows]))
            segment_info = {
                "start_row_index": int(segment_rows[0]),
                "end_row_index": int(segment_rows[-1]),
                "length": int(length),
                "peak_score": round(peak, 4),
            }
            if sorted_times is not None and len(sorted_times) > start:
                start_time = sorted_times.iloc[start]
                end_time = sorted_times.iloc[len(sorted_times) - 1]
                segment_info["start_time"] = start_time.isoformat() if pd.notna(start_time) else None
                segment_info["end_time"] = end_time.isoformat() if pd.notna(end_time) else None
            segments.append(segment_info)

    return flags, segments


def _detect_geospatial_anomalies(
    df: pd.DataFrame,
    profile: Dict[str, Any],
) -> Tuple[np.ndarray, Dict[int, List[str]], Dict[int, set[str]], Dict[str, Any]]:
    row_count = len(df)
    flags = np.zeros(row_count, dtype=bool)
    details: Dict[int, List[str]] = defaultdict(list)
    affected: Dict[int, set[str]] = defaultdict(set)
    metadata: Dict[str, Any] = {}

    geo_summary = profile.get("geospatial_summary", {})
    lat_col = geo_summary.get("latitude_column")
    lon_col = geo_summary.get("longitude_column")

    if not lat_col or not lon_col or lat_col not in df.columns or lon_col not in df.columns:
        return flags, details, affected, metadata

    lat = pd.to_numeric(df[lat_col], errors="coerce")
    lon = pd.to_numeric(df[lon_col], errors="coerce")
    valid = lat.between(-90, 90) & lon.between(-180, 180) & lat.notna() & lon.notna()

    if int(valid.sum()) < 12:
        return flags, details, affected, metadata

    lat_valid = lat[valid].to_numpy(dtype=float)
    lon_valid = lon[valid].to_numpy(dtype=float)

    center_lat = float(np.nanmedian(lat_valid))
    center_lon = float(np.nanmedian(lon_valid))

    lat_rad = np.radians(lat_valid)
    lon_rad = np.radians(lon_valid)
    center_lat_rad = np.radians(center_lat)
    center_lon_rad = np.radians(center_lon)

    dlat = lat_rad - center_lat_rad
    dlon = lon_rad - center_lon_rad
    a = np.sin(dlat / 2.0) ** 2 + np.cos(center_lat_rad) * np.cos(lat_rad) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(1.0 - a, 1e-12)))
    distance_km = 6371.0 * c

    med = float(np.nanmedian(distance_km))
    mad = float(np.nanmedian(np.abs(distance_km - med)))
    threshold = max(med + 6.0 * mad, float(np.nanquantile(distance_km, 0.995)))
    threshold = max(threshold, 0.5)

    valid_indices = np.where(valid.to_numpy())[0]
    outlier_local_positions = np.where(distance_km > threshold)[0]
    outlier_rows = valid_indices[outlier_local_positions]
    flags[outlier_rows] = True

    metadata = {
        "center_latitude": round(center_lat, 6),
        "center_longitude": round(center_lon, 6),
        "distance_threshold_km": round(float(threshold), 6),
    }

    for local_idx, row_idx in zip(outlier_local_positions.tolist(), outlier_rows.tolist()):
        row_lat = lat.iloc[row_idx]
        row_lon = lon.iloc[row_idx]
        row_distance = float(distance_km[local_idx])
        ratio = row_distance / threshold if threshold > 0 else np.nan
        message = (
            f"geospatial outlier at ({_format_metric(row_lat)}, {_format_metric(row_lon)}): "
            f"distance={_format_metric(row_distance)} km from median geo-center "
            f"({_format_metric(center_lat)}, {_format_metric(center_lon)}) exceeded threshold={_format_metric(threshold)} km "
            f"(strength={_format_metric(ratio)}x)"
        )
        details[row_idx].append(message)
        affected[row_idx].add(str(lat_col))
        affected[row_idx].add(str(lon_col))

    return flags, details, affected, metadata


def _detect_impossible_values(df: pd.DataFrame, column_types: Dict[str, str]) -> Dict[str, Any]:
    column_counts: Dict[str, int] = {}
    total = 0

    for col, col_type in column_types.items():
        if col_type != "numeric":
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        name = col.lower()
        count = 0

        if any(token in name for token in ["age", "qty", "quantity", "count", "duration", "days", "hours", "month"]):
            count += int((series < 0).sum())

        if any(token in name for token in ["percent", "pct"]):
            count += int(((series < 0) | (series > 100)).sum())

        if count > 0:
            column_counts[col] = int(count)
            total += int(count)

    return {
        "count": int(total),
        "columns": list(column_counts.keys()),
        "column_counts": column_counts,
    }


def _detect_inconsistent_categories(df: pd.DataFrame, column_types: Dict[str, str]) -> Dict[str, Any]:
    inconsistent_columns: Dict[str, int] = {}

    for col, col_type in column_types.items():
        if col_type not in {"categorical", "text"}:
            continue

        values = df[col].dropna().astype(str)
        if values.empty:
            continue
        if values.nunique() > 200:
            continue

        normalized = values.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
        raw_by_norm: Dict[str, set[str]] = defaultdict(set)
        for raw, norm in zip(values.tolist(), normalized.tolist()):
            raw_by_norm[norm].add(raw)

        inconsistent_norms = {norm for norm, raws in raw_by_norm.items() if len(raws) > 1}
        if not inconsistent_norms:
            continue

        count = int(normalized.isin(inconsistent_norms).sum())
        inconsistent_columns[col] = count

    total = int(sum(inconsistent_columns.values()))
    return {
        "count": total,
        "columns": list(inconsistent_columns.keys()),
        "column_counts": inconsistent_columns,
    }


def _quality_anomalies_summary(profile: Dict[str, Any], df: pd.DataFrame, column_types: Dict[str, str]) -> Dict[str, Any]:
    missing_map = profile.get("missing_values", {})
    missing_columns = [col for col, stats in missing_map.items() if float(stats.get("count", 0)) > 0]
    total_missing_cells = int(sum(float(stats.get("count", 0)) for stats in missing_map.values()))

    duplicate_rows = int(profile.get("duplicate_rows", 0))
    impossible_values = _detect_impossible_values(df, column_types)
    inconsistent_categories = _detect_inconsistent_categories(df, column_types)

    skewed_columns = list(profile.get("skewed_numeric_columns", {}).keys())
    invalid_dates = profile.get("invalid_dates", {})
    invalid_date_columns = [col for col, count in invalid_dates.items() if int(count) > 0]
    invalid_date_count = int(sum(int(count) for count in invalid_dates.values()))
    geospatial_summary = profile.get("geospatial_summary", {})
    lat_col = geospatial_summary.get("latitude_column")
    lon_col = geospatial_summary.get("longitude_column")
    invalid_geo_count = int(
        geospatial_summary.get("invalid_coordinate_pairs", 0)
        + geospatial_summary.get("missing_coordinate_pairs", 0)
        + geospatial_summary.get("invalid_latitude_values", 0)
        + geospatial_summary.get("invalid_longitude_values", 0)
    )
    geo_columns = [col for col in [lat_col, lon_col] if col]

    return {
        "missing_values": {
            "count": total_missing_cells,
            "columns": missing_columns,
        },
        "duplicates": {
            "count": duplicate_rows,
            "columns": [],
        },
        "impossible_values": impossible_values,
        "inconsistent_categories": inconsistent_categories,
        "extreme_skew": {
            "count": int(len(skewed_columns)),
            "columns": skewed_columns,
        },
        "invalid_dates": {
            "count": invalid_date_count,
            "columns": invalid_date_columns,
        },
        "invalid_geo_coordinates": {
            "count": invalid_geo_count,
            "columns": geo_columns,
        },
    }


def _build_explanation(
    anomaly_types: List[str],
    anomaly_score: float,
    severity: str,
    reason_details: List[str],
    triggered_methods: List[str],
    contextual_details: List[str],
    geospatial_details: List[str],
    time_details: List[str],
    affected_columns: List[str],
    time_column: str | None = None,
    time_value: Any = None,
) -> str:
    type_labels = [ANOMALY_TYPE_LABELS.get(item, item.replace("_", " ")) for item in anomaly_types]
    pieces = [
        f"Classified as {', '.join(type_labels)} with anomaly score {_format_metric(anomaly_score)} ({severity})."
    ]

    if reason_details:
        pieces.append(f"Why flagged: {'; '.join(reason_details[:3])}.")

    if triggered_methods:
        pieces.append(f"Detection signals: {', '.join(triggered_methods)}.")

    if affected_columns:
        pieces.append(f"Affected columns: {', '.join(affected_columns[:5])}.")

    if contextual_details:
        pieces.append(f"Context detail: {contextual_details[0]}.")

    if geospatial_details:
        pieces.append(f"Geospatial detail: {geospatial_details[0]}.")

    if time_details:
        pieces.append(f"Time-series detail: {time_details[0]}.")

    if time_column and time_value is not None and pd.notna(time_value):
        if hasattr(time_value, "isoformat"):
            time_str = time_value.isoformat()
        else:
            time_str = str(time_value)
        pieces.append(f"Timestamp context ({time_column}): {time_str}.")

    return " ".join(pieces)


def _build_action(anomaly_types: List[str], affected_columns: List[str]) -> str:
    if "geospatial_anomaly" in anomaly_types:
        return "Validate coordinate reference system, confirm geocoding quality, and inspect location-specific source records."

    if any(item.startswith("time_series_") for item in anomaly_types):
        return "Inspect adjacent time windows, verify event logs, and validate abrupt shifts before applying smoothing or caps."

    if "contextual_anomaly" in anomaly_types:
        return "Review this record within its category/time context and verify business rules for that segment."

    if "high_dimensional_multivariate_anomaly" in anomaly_types:
        return "Validate cross-feature relationships and source joins for this record before remediation."

    if "collective_anomaly" in anomaly_types:
        return "Investigate the surrounding run of records as a sequence-level incident, not in isolation."

    if affected_columns:
        cols = ", ".join(affected_columns[:3])
        return f"Verify source values for {cols}; correct entry errors and cap impossible extremes where justified."

    return "Review this record against data contracts and source-system audit trails."


def detect_anomalies(
    df: pd.DataFrame,
    column_types: Dict[str, str],
    profile: Dict[str, Any] | None = None,
    top_n: int = 100,
) -> Dict[str, Any]:
    profile = profile or {}
    numeric_columns = [col for col, col_type in column_types.items() if col_type == "numeric"]
    row_count = int(len(df))

    if not numeric_columns:
        quality = _quality_anomalies_summary(profile, df, column_types)
        breakdown = {
            "point_anomalies_global_outliers": 0,
            "contextual_anomalies": 0,
            "collective_anomalies": 0,
            "time_series_spikes": 0,
            "time_series_dips": 0,
            "time_series_trend_changes": 0,
            "time_series_seasonal_breaks": 0,
            "high_dimensional_multivariate_anomalies": 0,
            "geospatial_anomalies": 0,
            "data_quality_missing_values": int(quality["missing_values"]["count"]),
            "data_quality_duplicates": int(quality["duplicates"]["count"]),
            "data_quality_impossible_values": int(quality["impossible_values"]["count"]),
            "data_quality_inconsistent_categories": int(quality["inconsistent_categories"]["count"]),
            "data_quality_extreme_skew": int(quality["extreme_skew"]["count"]),
            "data_quality_invalid_dates": int(quality["invalid_dates"]["count"]),
            "data_quality_invalid_geo_coordinates": int(quality["invalid_geo_coordinates"]["count"]),
        }
        return {
            "total_rows": row_count,
            "suspicious_count": 0,
            "severity_breakdown": {"critical": 0, "high": 0, "medium": 0, "low": row_count},
            "anomaly_type_breakdown": breakdown,
            "anomaly_category_breakdown": {
                "point_global": 0,
                "contextual": 0,
                "collective": 0,
                "time_series": 0,
                "multivariate": 0,
                "geospatial": 0,
                "data_quality": int(sum(int(payload.get("count", 0)) for payload in quality.values())),
            },
            "anomaly_groups": _build_anomaly_groups([], quality),
            "quality_anomalies": quality,
            "time_series_events": [],
            "collective_anomaly_segments": [],
            "anomaly_score_distribution": [],
            "records": [],
            "_all_scores": np.zeros(row_count, dtype=float),
        }

    feature_df = df[numeric_columns].copy()
    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)
    medians = feature_df.median(numeric_only=True)
    feature_df = feature_df.fillna(medians)

    values = feature_df.to_numpy(dtype=float).astype(np.float32, copy=False)

    iqr_flags = np.zeros((row_count, len(numeric_columns)), dtype=bool)
    zscore_flags = np.zeros((row_count, len(numeric_columns)), dtype=bool)
    zscore_strength = np.zeros((row_count, len(numeric_columns)), dtype=float)
    lower_bounds = np.full(len(numeric_columns), np.nan, dtype=float)
    upper_bounds = np.full(len(numeric_columns), np.nan, dtype=float)
    means = np.full(len(numeric_columns), np.nan, dtype=float)
    stds = np.full(len(numeric_columns), np.nan, dtype=float)

    for idx, col in enumerate(numeric_columns):
        col_values = feature_df[col].astype(float)

        q1 = col_values.quantile(0.25)
        q3 = col_values.quantile(0.75)
        iqr = q3 - q1
        if not np.isclose(iqr, 0.0):
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            lower_bounds[idx] = float(lower)
            upper_bounds[idx] = float(upper)
            iqr_flags[:, idx] = (col_values < lower) | (col_values > upper)

        mean = float(col_values.mean())
        std = float(col_values.std(ddof=0))
        means[idx] = mean
        stds[idx] = std
        if not np.isclose(std, 0.0):
            zscores = np.abs((col_values - mean) / std)
            zscore_strength[:, idx] = zscores
            zscore_flags[:, idx] = zscores > 3

    iqr_any = iqr_flags.any(axis=1)
    zscore_any = zscore_flags.any(axis=1)
    iqr_ratio = iqr_flags.sum(axis=1) / max(1, len(numeric_columns))
    zscore_peak = np.clip(zscore_strength.max(axis=1) / 3.0, 0, 1)

    large_dataset_mode = row_count > LARGE_DATASET_ROW_THRESHOLD

    train_values = values
    if large_dataset_mode:
        sample_size = min(MAX_TRAIN_ROWS, row_count)
        rng = np.random.default_rng(seed=42)
        sample_indices = rng.choice(row_count, size=sample_size, replace=False)
        train_values = values[sample_indices]

    model_jobs = MODEL_JOBS
    isolation_forest = IsolationForest(
        n_estimators=160,
        random_state=42,
        contamination="auto",
        n_jobs=model_jobs,
    )
    try:
        isolation_forest.fit(train_values)
    except Exception as exc:  # noqa: BLE001
        if model_jobs == 1:
            raise
        isolation_forest = IsolationForest(
            n_estimators=160,
            random_state=42,
            contamination="auto",
            n_jobs=1,
        )
        isolation_forest.fit(train_values)
        model_jobs = 1
    iso_pred = isolation_forest.predict(values)
    iso_raw = -isolation_forest.decision_function(values)
    iso_norm = _normalize(iso_raw)

    if row_count > 2 and len(train_values) > 2:
        n_neighbors = min(20, max(2, len(train_values) - 1))
        if large_dataset_mode:
            lof = LocalOutlierFactor(
                n_neighbors=n_neighbors,
                contamination="auto",
                novelty=True,
                n_jobs=model_jobs,
            )
            try:
                lof.fit(train_values)
                lof_pred = lof.predict(values)
                lof_raw = -lof.decision_function(values)
            except Exception:  # noqa: BLE001
                if model_jobs == 1:
                    raise
                lof = LocalOutlierFactor(
                    n_neighbors=n_neighbors,
                    contamination="auto",
                    novelty=True,
                    n_jobs=1,
                )
                lof.fit(train_values)
                lof_pred = lof.predict(values)
                lof_raw = -lof.decision_function(values)
        else:
            lof = LocalOutlierFactor(
                n_neighbors=n_neighbors,
                contamination="auto",
                n_jobs=model_jobs,
            )
            try:
                lof_pred = lof.fit_predict(values)
                lof_raw = -lof.negative_outlier_factor_
            except Exception:  # noqa: BLE001
                if model_jobs == 1:
                    raise
                lof = LocalOutlierFactor(
                    n_neighbors=n_neighbors,
                    contamination="auto",
                    n_jobs=1,
                )
                lof_pred = lof.fit_predict(values)
                lof_raw = -lof.negative_outlier_factor_
        lof_norm = _normalize(lof_raw)
    else:
        lof_pred = np.ones(row_count, dtype=int)
        lof_norm = np.zeros(row_count, dtype=float)

    method_votes = (
        iqr_any.astype(float)
        + zscore_any.astype(float)
        + (iso_pred == -1).astype(float)
        + (lof_pred == -1).astype(float)
    ) / 4.0

    anomaly_scores = np.clip(
        (0.36 * method_votes) + (0.2 * iqr_ratio) + (0.2 * zscore_peak) + (0.14 * iso_norm) + (0.1 * lof_norm),
        0,
        1,
    )

    point_flags = iqr_any | zscore_any
    high_dim_flags = ((iso_pred == -1) & (lof_pred == -1)) | (iso_norm > 0.8)

    contextual_flags, contextual_details, contextual_affected = _detect_contextual_anomalies(
        df,
        feature_df,
        numeric_columns,
        column_types,
    )

    time_col, parsed_time = _detect_best_time_column(df, column_types)
    if time_col is not None and parsed_time is not None:
        sorted_indices = np.argsort(parsed_time.fillna(pd.Timestamp.max).to_numpy())
        sorted_times = parsed_time.iloc[sorted_indices].reset_index(drop=True)
    else:
        sorted_indices = np.arange(row_count)
        sorted_times = None

    collective_threshold = (
        max(0.58, float(np.quantile(anomaly_scores[sorted_indices], 0.9)))
        if row_count >= 6
        else 0.58
    )

    time_flags, time_events, time_affected, time_details = _detect_time_series_anomalies(
        feature_df,
        sorted_indices,
        sorted_times if sorted_times is not None else pd.Series(dtype="datetime64[ns]"),
        numeric_columns,
    )

    collective_flags, collective_segments = _detect_collective_anomalies(
        anomaly_scores,
        sorted_indices,
        sorted_times,
    )
    geospatial_flags, geospatial_details, geospatial_affected, _geospatial_meta = _detect_geospatial_anomalies(
        df,
        profile,
    )

    severity_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    candidate_rows: List[Dict[str, Any]] = []

    for row_idx in range(row_count):
        score = float(anomaly_scores[row_idx])
        sev = _severity(score)
        severity_breakdown[sev] += 1

        triggered_methods: List[str] = []
        if iqr_any[row_idx]:
            triggered_methods.append("IQR")
        if zscore_any[row_idx]:
            triggered_methods.append("z-score")
        if iso_pred[row_idx] == -1:
            triggered_methods.append("Isolation Forest")
        if lof_pred[row_idx] == -1:
            triggered_methods.append("Local Outlier Factor")

        anomaly_types: List[str] = []
        if point_flags[row_idx]:
            anomaly_types.append("point_anomaly_global_outlier")
        if contextual_flags[row_idx]:
            anomaly_types.append("contextual_anomaly")
        if collective_flags[row_idx]:
            anomaly_types.append("collective_anomaly")
        if high_dim_flags[row_idx]:
            anomaly_types.append("high_dimensional_multivariate_anomaly")
        if geospatial_flags[row_idx]:
            anomaly_types.append("geospatial_anomaly")

        for ts_type in [
            "time_series_spike",
            "time_series_dip",
            "time_series_trend_change",
            "time_series_seasonal_break",
        ]:
            if time_flags[ts_type][row_idx]:
                anomaly_types.append(ts_type)

        if not anomaly_types:
            continue

        reason_details: List[str] = []
        for col_idx, col_name in enumerate(numeric_columns):
            if not (iqr_flags[row_idx, col_idx] or zscore_flags[row_idx, col_idx]):
                continue

            col_value = float(feature_df.iloc[row_idx, col_idx])
            has_iqr = bool(iqr_flags[row_idx, col_idx])
            has_z = bool(zscore_flags[row_idx, col_idx])

            if has_iqr and np.isfinite(lower_bounds[col_idx]) and np.isfinite(upper_bounds[col_idx]) and has_z:
                reason_details.append(
                    f"{col_name}={_format_metric(col_value)} outside IQR [{_format_metric(lower_bounds[col_idx])}, {_format_metric(upper_bounds[col_idx])}] and z-score={_format_metric(zscore_strength[row_idx, col_idx])} (>3.0)"
                )
            elif has_iqr and np.isfinite(lower_bounds[col_idx]) and np.isfinite(upper_bounds[col_idx]):
                reason_details.append(
                    f"{col_name}={_format_metric(col_value)} outside IQR [{_format_metric(lower_bounds[col_idx])}, {_format_metric(upper_bounds[col_idx])}]"
                )
            elif has_z:
                reason_details.append(
                    f"{col_name} z-score={_format_metric(zscore_strength[row_idx, col_idx])} (>3.0) vs mean={_format_metric(means[col_idx])}, std={_format_metric(stds[col_idx])}"
                )

            if len(reason_details) >= 3:
                break

        if high_dim_flags[row_idx]:
            reason_details.append(
                f"multivariate profile is isolated (IsolationForest={_format_metric(iso_norm[row_idx])}, LOF={_format_metric(lof_norm[row_idx])})"
            )

        if collective_flags[row_idx]:
            reason_details.append(
                f"part of a consecutive high-score sequence (segment threshold={_format_metric(collective_threshold)})"
            )
        if geospatial_flags[row_idx]:
            reason_details.append(
                geospatial_details.get(row_idx, ["geospatial outlier relative to dataset location distribution"])[0]
            )

        affected_indices = np.where(iqr_flags[row_idx] | zscore_flags[row_idx])[0].tolist()
        affected_columns = [numeric_columns[i] for i in affected_indices]
        affected_columns.extend(sorted(contextual_affected.get(row_idx, set())))
        affected_columns.extend(sorted(time_affected.get(row_idx, set())))
        affected_columns.extend(sorted(geospatial_affected.get(row_idx, set())))

        if not affected_columns:
            top_idx = np.argsort(zscore_strength[row_idx])[-3:]
            affected_columns = [
                numeric_columns[i]
                for i in top_idx
                if zscore_strength[row_idx, i] > 0
            ]

        affected_columns = list(dict.fromkeys(affected_columns))

        record_payload = {
            str(col): to_serializable(value)
            for col, value in df.iloc[row_idx].to_dict().items()
        }

        explanation = _build_explanation(
            anomaly_types,
            score,
            sev,
            reason_details,
            triggered_methods,
            contextual_details.get(row_idx, []),
            geospatial_details.get(row_idx, []),
            time_details.get(row_idx, []),
            affected_columns,
            time_col,
            parsed_time.iloc[row_idx] if parsed_time is not None else None,
        )
        anomaly_categories = list(dict.fromkeys([_type_to_category(item) for item in anomaly_types]))
        primary_category = _primary_category(anomaly_categories)

        candidate_rows.append(
            {
                "row_index": int(row_idx),
                "anomaly_score": round(score, 4),
                "severity": sev,
                "anomaly_types": anomaly_types,
                "anomaly_categories": anomaly_categories,
                "primary_category": primary_category,
                "explanation": explanation,
                "affected_columns": affected_columns,
                "recommended_action": _build_action(anomaly_types, affected_columns),
                "record": record_payload,
            }
        )

    types_requiring_visibility = {
        "contextual_anomaly",
        "collective_anomaly",
        "time_series_spike",
        "time_series_dip",
        "time_series_trend_change",
        "time_series_seasonal_break",
        "high_dimensional_multivariate_anomaly",
        "geospatial_anomaly",
    }

    suspicious = [
        row
        for row in candidate_rows
        if row["severity"] in {"critical", "high", "medium"}
        or bool(types_requiring_visibility.intersection(set(row["anomaly_types"])))
    ]
    suspicious.sort(key=lambda item: (item["anomaly_score"], len(item["anomaly_types"])), reverse=True)

    score_distribution = [
        {
            "row_index": int(idx),
            "score": round(float(score), 4),
        }
        for idx, score in sorted(
            enumerate(anomaly_scores.tolist()),
            key=lambda item: item[1],
            reverse=True,
        )[: min(400, row_count)]
    ]

    quality = _quality_anomalies_summary(profile, df, column_types)

    anomaly_type_breakdown = {
        "point_anomalies_global_outliers": int(point_flags.sum()),
        "contextual_anomalies": int(contextual_flags.sum()),
        "collective_anomalies": int(collective_flags.sum()),
        "time_series_spikes": int(time_flags["time_series_spike"].sum()),
        "time_series_dips": int(time_flags["time_series_dip"].sum()),
        "time_series_trend_changes": int(time_flags["time_series_trend_change"].sum()),
        "time_series_seasonal_breaks": int(time_flags["time_series_seasonal_break"].sum()),
        "high_dimensional_multivariate_anomalies": int(high_dim_flags.sum()),
        "geospatial_anomalies": int(geospatial_flags.sum()),
        "data_quality_missing_values": int(quality["missing_values"]["count"]),
        "data_quality_duplicates": int(quality["duplicates"]["count"]),
        "data_quality_impossible_values": int(quality["impossible_values"]["count"]),
        "data_quality_inconsistent_categories": int(quality["inconsistent_categories"]["count"]),
        "data_quality_extreme_skew": int(quality["extreme_skew"]["count"]),
        "data_quality_invalid_dates": int(quality["invalid_dates"]["count"]),
        "data_quality_invalid_geo_coordinates": int(quality["invalid_geo_coordinates"]["count"]),
    }
    anomaly_category_breakdown = {
        "point_global": int(point_flags.sum()),
        "contextual": int(contextual_flags.sum()),
        "collective": int(collective_flags.sum()),
        "time_series": int(
            time_flags["time_series_spike"].sum()
            + time_flags["time_series_dip"].sum()
            + time_flags["time_series_trend_change"].sum()
            + time_flags["time_series_seasonal_break"].sum()
        ),
        "multivariate": int(high_dim_flags.sum()),
        "geospatial": int(geospatial_flags.sum()),
        "data_quality": int(sum(int(payload.get("count", 0)) for payload in quality.values())),
    }
    anomaly_groups = _build_anomaly_groups(suspicious, quality)

    return {
        "total_rows": row_count,
        "suspicious_count": len(suspicious),
        "severity_breakdown": severity_breakdown,
        "anomaly_type_breakdown": anomaly_type_breakdown,
        "anomaly_category_breakdown": anomaly_category_breakdown,
        "anomaly_groups": anomaly_groups,
        "quality_anomalies": quality,
        "time_series_events": time_events,
        "collective_anomaly_segments": collective_segments,
        "anomaly_score_distribution": score_distribution,
        "records": suspicious[:top_n],
        "_all_scores": anomaly_scores,
    }
