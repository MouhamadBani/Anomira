from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from app.schemas.data_schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnomalyRequest,
    AnomalyResponse,
    AsyncAnalyzeUrlRequest,
    JobCreatedResponse,
    JobStatusResponse,
    ProfileRequest,
    ProfileResponse,
    ReportRequest,
    UploadCapabilitiesResponse,
    UploadResponse,
    UploadUrlRequest,
)
from app.services.anomaly_service import detect_anomalies
from app.services.data_store import DatasetNotFoundError, dataset_store
from app.services.file_service import (
    MAX_CLOUD_DOWNLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_BYTES,
    STREAM_CHUNK_SIZE,
    FileParsingError,
    FileValidationError,
    download_cloud_url_to_temp_file,
    extract_upload_metadata_from_path,
    get_upload_capabilities,
    validate_filename,
)
from app.services.job_service import JobNotFoundError, job_store
from app.services.profile_service import profile_dataset
from app.services.recommendation_service import generate_auto_fix_plan, generate_recommendations
from app.services.report_service import generate_html_report
from app.services.tb_analysis_service import (
    LargeAnalysisError,
    analyze_large_dataset_from_path,
    should_use_chunked_mode,
)

router = APIRouter(prefix="/api", tags=["Data Intelligence"])

ProgressCallback = Callable[[float, str], None]


def _stream_upload_to_temp(suffix: str) -> str:
    fd, temp_path = tempfile.mkstemp(prefix="anomira_upload_", suffix=suffix)
    os.close(fd)
    return temp_path


def _cleanup_temp(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _emit_progress(progress_callback: ProgressCallback | None, progress: float, message: str) -> None:
    if progress_callback is None:
        return
    progress_callback(progress, message)


def _compute_analysis(
    entry,
    dataframe,
    top_n: int,
    expected_columns: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[dict, dict, list[str], list[dict]]:
    cached = dataset_store.get_cached_analysis(entry, top_n, expected_columns)
    if cached is not None:
        _emit_progress(progress_callback, 96.0, "Using cached analysis results.")
        return (
            cached["profile"],
            cached["anomalies"],
            cached["recommendations"],
            cached["auto_fix_plan"],
        )

    # TB-ready path: run chunked sampled mode directly from staged source file.
    if entry.source_path is not None and should_use_chunked_mode(entry.source_path, entry.filename):
        try:
            profile, anomalies, recommendations, auto_fix_plan, metadata = analyze_large_dataset_from_path(
                entry.source_path,
                entry.filename,
                top_n=top_n,
                expected_columns=expected_columns,
                progress_callback=progress_callback,
            )
        except LargeAnalysisError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        anomalies.setdefault("analysis_metadata", {})
        anomalies["analysis_metadata"].update(metadata)
        entry.profile_cache = profile

        dataset_store.set_cached_analysis(
            entry,
            top_n,
            expected_columns,
            {
                "profile": profile,
                "anomalies": anomalies,
                "recommendations": recommendations,
                "auto_fix_plan": auto_fix_plan,
            },
        )
        return profile, anomalies, recommendations, auto_fix_plan

    # Default path: full dataframe in-memory mode.
    if dataframe is None:
        _emit_progress(progress_callback, 64.0, "Loading dataset into memory.")
        dataframe = dataset_store.ensure_dataframe(entry)

    _emit_progress(progress_callback, 70.0, "Profiling dataset columns and quality issues.")
    profile = dataset_store.get_or_compute_profile(entry, dataframe, profile_dataset)

    _emit_progress(progress_callback, 79.0, "Running anomaly detection engines.")
    anomalies = detect_anomalies(
        dataframe,
        profile["column_types"],
        profile=profile,
        top_n=top_n,
    )
    anomalies.setdefault("analysis_metadata", {})
    anomalies["analysis_metadata"].update(
        {
            "analysis_mode": "full_dataframe",
            "approximate": False,
            "sampled_rows": int(len(dataframe)),
            "sampled_ratio": 1.0,
        }
    )

    _emit_progress(progress_callback, 88.0, "Generating recommendations and auto-fix plan.")
    recommendations = generate_recommendations(profile, anomalies, expected_columns=expected_columns)
    auto_fix_plan = generate_auto_fix_plan(profile, anomalies, expected_columns=expected_columns)
    anomalies.pop("_all_scores", None)

    dataset_store.set_cached_analysis(
        entry,
        top_n,
        expected_columns,
        {
            "profile": profile,
            "anomalies": anomalies,
            "recommendations": recommendations,
            "auto_fix_plan": auto_fix_plan,
        },
    )
    return profile, anomalies, recommendations, auto_fix_plan


def _upload_payload_from_entry(entry) -> dict:
    return {
        "dataset_id": entry.dataset_id,
        "filename": entry.filename,
        "row_count": entry.row_count,
        "column_count": entry.column_count,
        "columns": entry.columns,
        "preview": entry.preview,
    }


def _run_analyze_url_job(job_id: str, payload: AsyncAnalyzeUrlRequest) -> None:
    temp_path: str | None = None
    try:
        job_store.update(
            job_id,
            status="running",
            stage="downloading",
            progress=2.0,
            message="Downloading dataset from cloud URL.",
            started=True,
        )

        def on_download(downloaded: int, total: int | None) -> None:
            if total and total > 0:
                ratio = max(0.0, min(1.0, downloaded / float(total)))
                progress = 2.0 + (ratio * 31.0)
                message = (
                    f"Downloading cloud dataset... {round(downloaded / (1024 * 1024), 2)}MB / "
                    f"{round(total / (1024 * 1024), 2)}MB"
                )
            else:
                # When no Content-Length exists, keep visual progress smooth but bounded.
                inferred_ratio = max(0.0, min(1.0, downloaded / float(2 * 1024 * 1024 * 1024)))
                progress = 2.0 + (inferred_ratio * 20.0)
                message = f"Downloading cloud dataset... {round(downloaded / (1024 * 1024), 2)}MB"
            job_store.update(job_id, progress=progress, message=message)

        filename, temp_file_path, downloaded_size = download_cloud_url_to_temp_file(
            payload.url,
            filename_hint=payload.filename,
            progress_callback=on_download,
        )
        temp_path = str(temp_file_path)

        job_store.update(
            job_id,
            stage="profiling",
            progress=35.0,
            message="Extracting metadata and preparing analysis.",
            metadata={"source_size_bytes": int(downloaded_size)},
        )

        metadata = extract_upload_metadata_from_path(
            temp_path,
            filename,
            max_size_bytes=MAX_CLOUD_DOWNLOAD_SIZE_BYTES,
            size_label="Cloud file",
        )

        entry = dataset_store.create(
            filename,
            file_bytes=None,
            file_path=temp_path,
            row_count=metadata["row_count"],
            column_count=metadata["column_count"],
            columns=metadata["columns"],
            preview=metadata["preview"],
        )
        temp_path = None
        dataset_payload = _upload_payload_from_entry(entry)

        job_store.update(
            job_id,
            stage="analyzing",
            progress=42.0,
            message="Running anomaly analysis pipeline.",
            dataset=dataset_payload,
        )

        def on_analysis(progress: float, message: str) -> None:
            # Analysis sub-progress is in [35..96], map directly but clamp.
            mapped = max(35.0, min(96.0, float(progress)))
            job_store.update(job_id, stage="analyzing", progress=mapped, message=message)

        profile, anomalies, recommendations, auto_fix_plan = _compute_analysis(
            entry,
            dataframe=None,
            top_n=payload.top_n or 100,
            expected_columns=payload.expected_columns,
            progress_callback=on_analysis,
        )

        analysis_payload = {
            "dataset_id": entry.dataset_id,
            "profile": ProfileResponse(dataset_id=entry.dataset_id, **profile).model_dump(),
            "anomalies": AnomalyResponse(
                dataset_id=entry.dataset_id,
                recommendations=recommendations,
                auto_fix_plan=auto_fix_plan,
                **anomalies,
            ).model_dump(),
        }

        metadata_payload = {
            "analysis_mode": anomalies.get("analysis_metadata", {}).get("analysis_mode", "full_dataframe"),
            "approximate": bool(anomalies.get("analysis_metadata", {}).get("approximate", False)),
            "sampled_rows": anomalies.get("analysis_metadata", {}).get("sampled_rows"),
            "sampled_ratio": anomalies.get("analysis_metadata", {}).get("sampled_ratio"),
            "source_size_bytes": int(downloaded_size),
            "tb_ready_async": True,
        }

        job_store.update(
            job_id,
            status="completed",
            stage="completed",
            progress=100.0,
            message="Analysis completed successfully.",
            analysis=analysis_payload,
            metadata=metadata_payload,
            finished=True,
        )
    except FileValidationError as exc:
        _cleanup_temp(temp_path)
        job_store.update(
            job_id,
            status="failed",
            stage="failed",
            progress=100.0,
            message="Job failed during validation.",
            error=str(exc),
            finished=True,
        )
    except FileParsingError as exc:
        _cleanup_temp(temp_path)
        job_store.update(
            job_id,
            status="failed",
            stage="failed",
            progress=100.0,
            message="Job failed while parsing cloud dataset.",
            error=str(exc),
            finished=True,
        )
    except HTTPException as exc:
        _cleanup_temp(temp_path)
        job_store.update(
            job_id,
            status="failed",
            stage="failed",
            progress=100.0,
            message="Job failed during analysis.",
            error=str(exc.detail),
            finished=True,
        )
    except Exception as exc:  # noqa: BLE001
        _cleanup_temp(temp_path)
        job_store.update(
            job_id,
            status="failed",
            stage="failed",
            progress=100.0,
            message="Unexpected error in async analysis job.",
            error=str(exc),
            finished=True,
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)) -> UploadResponse:
    temp_path: str | None = None
    try:
        filename, suffix = validate_filename(file.filename or "")
        temp_path = _stream_upload_to_temp(suffix)

        total_size = 0
        with open(temp_path, "wb") as destination:
            while True:
                chunk = await file.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if MAX_UPLOAD_SIZE_BYTES is not None and total_size > MAX_UPLOAD_SIZE_BYTES:
                    raise FileValidationError(
                        f"File size exceeds max allowed size of {round(MAX_UPLOAD_SIZE_BYTES / (1024 * 1024), 2)}MB."
                    )
                destination.write(chunk)

        if total_size == 0:
            raise FileParsingError("Uploaded file is empty")

        metadata = extract_upload_metadata_from_path(
            temp_path,
            filename,
            max_size_bytes=MAX_UPLOAD_SIZE_BYTES,
            size_label="File",
        )
    except FileValidationError as exc:
        _cleanup_temp(temp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileParsingError as exc:
        _cleanup_temp(temp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _cleanup_temp(temp_path)
        raise HTTPException(status_code=400, detail=f"Failed to upload dataset: {exc}") from exc

    entry = dataset_store.create(
        filename,
        file_bytes=None,
        file_path=temp_path,
        row_count=metadata["row_count"],
        column_count=metadata["column_count"],
        columns=metadata["columns"],
        preview=metadata["preview"],
    )

    return UploadResponse(**_upload_payload_from_entry(entry))


@router.post("/upload-url", response_model=UploadResponse)
def upload_dataset_from_url(payload: UploadUrlRequest) -> UploadResponse:
    temp_path = None
    try:
        filename, temp_file_path, _ = download_cloud_url_to_temp_file(payload.url, filename_hint=payload.filename)
        temp_path = str(temp_file_path)
        metadata = extract_upload_metadata_from_path(
            temp_path,
            filename,
            max_size_bytes=MAX_CLOUD_DOWNLOAD_SIZE_BYTES,
            size_label="Cloud file",
        )
    except FileValidationError as exc:
        _cleanup_temp(temp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileParsingError as exc:
        _cleanup_temp(temp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _cleanup_temp(temp_path)
        raise HTTPException(status_code=400, detail=f"Failed to download cloud dataset: {exc}") from exc

    entry = dataset_store.create(
        filename,
        file_bytes=None,
        file_path=temp_path,
        row_count=metadata["row_count"],
        column_count=metadata["column_count"],
        columns=metadata["columns"],
        preview=metadata["preview"],
    )
    return UploadResponse(**_upload_payload_from_entry(entry))


@router.post("/jobs/analyze-url", response_model=JobCreatedResponse)
def analyze_dataset_from_url_async(payload: AsyncAnalyzeUrlRequest) -> JobCreatedResponse:
    job = job_store.create(
        job_type="analyze_url",
        message="Job queued for cloud dataset analysis.",
        metadata={
            "top_n": payload.top_n or 100,
            "expected_columns_count": len(payload.expected_columns or []),
            "tb_ready_async": True,
        },
    )

    worker = threading.Thread(
        target=_run_analyze_url_job,
        args=(job.job_id, payload),
        daemon=True,
        name=f"anomira-job-{job.job_id[:8]}",
    )
    worker.start()

    return JobCreatedResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        message=job.message,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    try:
        payload = job_store.snapshot(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobStatusResponse(**payload)


@router.get("/capabilities", response_model=UploadCapabilitiesResponse)
def upload_capabilities() -> UploadCapabilitiesResponse:
    data = get_upload_capabilities()
    data["tb_ready_async_job_enabled"] = True
    data["chunked_tb_mode_formats"] = [".csv", ".tsv", ".txt", ".jsonl"]
    data["tb_mode_trigger_mb"] = int(os.getenv("ANOMIRA_TB_MODE_TRIGGER_MB", "512"))
    return UploadCapabilitiesResponse(**data)


@router.post("/profile", response_model=ProfileResponse)
def profile_data(payload: ProfileRequest) -> ProfileResponse:
    try:
        entry = dataset_store.get(payload.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Fast path if profile already exists.
    if entry.profile_cache is not None:
        return ProfileResponse(dataset_id=payload.dataset_id, **entry.profile_cache)

    profile, _, _, _ = _compute_analysis(
        entry,
        dataframe=None,
        top_n=30,
        expected_columns=None,
    )
    return ProfileResponse(dataset_id=payload.dataset_id, **profile)


@router.post("/anomalies", response_model=AnomalyResponse)
def analyze_anomalies(payload: AnomalyRequest) -> AnomalyResponse:
    try:
        entry = dataset_store.get(payload.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _, anomalies, recommendations, auto_fix_plan = _compute_analysis(
        entry,
        dataframe=None,
        top_n=payload.top_n or 100,
        expected_columns=payload.expected_columns,
    )

    return AnomalyResponse(
        dataset_id=payload.dataset_id,
        recommendations=recommendations,
        auto_fix_plan=auto_fix_plan,
        **anomalies,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_dataset(payload: AnalyzeRequest) -> AnalyzeResponse:
    try:
        entry = dataset_store.get(payload.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    profile, anomalies, recommendations, auto_fix_plan = _compute_analysis(
        entry,
        dataframe=None,
        top_n=payload.top_n or 100,
        expected_columns=payload.expected_columns,
    )

    profile_response = ProfileResponse(dataset_id=payload.dataset_id, **profile)
    anomaly_response = AnomalyResponse(
        dataset_id=payload.dataset_id,
        recommendations=recommendations,
        auto_fix_plan=auto_fix_plan,
        **anomalies,
    )
    return AnalyzeResponse(
        dataset_id=payload.dataset_id,
        profile=profile_response,
        anomalies=anomaly_response,
    )


@router.post("/report")
def build_report(payload: ReportRequest) -> HTMLResponse:
    try:
        entry = dataset_store.get(payload.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    profile, anomalies, recommendations, auto_fix_plan = _compute_analysis(
        entry,
        dataframe=None,
        top_n=payload.top_n or 100,
        expected_columns=payload.expected_columns,
    )

    html = generate_html_report(entry.filename, profile, anomalies, recommendations, auto_fix_plan)

    headers = {
        "Content-Disposition": 'attachment; filename="anomira-report.html"',
    }
    return HTMLResponse(content=html, headers=headers)
