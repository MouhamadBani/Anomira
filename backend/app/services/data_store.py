from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import pandas as pd

from app.services.file_service import load_dataframe, load_dataframe_from_path


class DatasetNotFoundError(Exception):
    pass


@dataclass
class DatasetEntry:
    dataset_id: str
    filename: str
    uploaded_at: datetime
    source_bytes: Optional[bytes]
    source_path: Optional[str]
    row_count: int
    column_count: int
    columns: list[str]
    preview: list[dict[str, Any]]
    dataframe: Optional[pd.DataFrame] = None
    profile_cache: Optional[dict[str, Any]] = None
    analysis_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    parse_lock: threading.Lock = field(default_factory=threading.Lock)

    def cache_key(self, top_n: int, expected_columns: list[str] | None) -> str:
        payload = {"top_n": top_n, "expected_columns": expected_columns or []}
        return json.dumps(payload, sort_keys=True)


class DatasetStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._datasets: Dict[str, DatasetEntry] = {}

    def create(
        self,
        filename: str,
        file_bytes: bytes | None,
        file_path: str | None,
        row_count: int,
        column_count: int,
        columns: list[str],
        preview: list[dict[str, Any]],
    ) -> DatasetEntry:
        if file_bytes is None and file_path is None:
            raise ValueError("Either file_bytes or file_path must be provided")

        dataset_id = uuid4().hex
        entry = DatasetEntry(
            dataset_id=dataset_id,
            filename=filename,
            uploaded_at=datetime.utcnow(),
            source_bytes=file_bytes,
            source_path=file_path,
            row_count=row_count,
            column_count=column_count,
            columns=columns,
            preview=preview,
        )

        with self._lock:
            self._datasets[dataset_id] = entry

        return entry

    def get(self, dataset_id: str) -> DatasetEntry:
        with self._lock:
            entry = self._datasets.get(dataset_id)

        if entry is None:
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' was not found")

        return entry

    def ensure_dataframe(self, entry: DatasetEntry) -> pd.DataFrame:
        with entry.parse_lock:
            if entry.dataframe is not None:
                return entry.dataframe

            if entry.source_path is not None:
                source_path = entry.source_path
                dataframe = load_dataframe_from_path(source_path, entry.filename)
                entry.dataframe = dataframe
                try:
                    import os

                    os.remove(source_path)
                except OSError:
                    pass
                entry.source_path = None
                entry.source_bytes = None
                return dataframe

            if entry.source_bytes is None:
                raise DatasetNotFoundError(f"Dataset '{entry.dataset_id}' source is unavailable")

            dataframe = load_dataframe(entry.source_bytes, entry.filename)
            entry.dataframe = dataframe
            # Free raw bytes after parsing to reduce memory pressure.
            entry.source_bytes = None
            entry.source_path = None
            return dataframe

    def get_cached_analysis(
        self,
        entry: DatasetEntry,
        top_n: int,
        expected_columns: list[str] | None,
    ) -> Optional[dict[str, Any]]:
        key = entry.cache_key(top_n, expected_columns)
        return entry.analysis_cache.get(key)

    def set_cached_analysis(
        self,
        entry: DatasetEntry,
        top_n: int,
        expected_columns: list[str] | None,
        value: dict[str, Any],
    ) -> None:
        key = entry.cache_key(top_n, expected_columns)
        entry.analysis_cache[key] = value

    def get_or_compute_profile(self, entry: DatasetEntry, dataframe: pd.DataFrame, compute_fn) -> dict[str, Any]:
        if entry.profile_cache is None:
            entry.profile_cache = compute_fn(dataframe)
        return entry.profile_cache


dataset_store = DatasetStore()
