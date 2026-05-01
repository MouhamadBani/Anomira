from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def to_serializable(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()

    if isinstance(value, np.generic):
        return value.item()

    if pd.isna(value):
        return None

    return value


def dataframe_preview(df: pd.DataFrame, limit: int = 10) -> List[Dict[str, Any]]:
    preview = df.head(limit)
    records: List[Dict[str, Any]] = []

    for _, row in preview.iterrows():
        record = {str(col): to_serializable(value) for col, value in row.items()}
        records.append(record)

    return records


def dataframe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        record = {str(col): to_serializable(value) for col, value in row.items()}
        records.append(record)

    return records
