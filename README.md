# Anomira MVP

Anomira is an automatic data intelligence and anomaly detection platform that profiles uploaded datasets, identifies suspicious records, recommends fixes, and exports a branded HTML report.

## Branding
- Name: **Anomira**
- Tagline: **Automatic Data Intelligence & Anomaly Detection System**
- Official logo path: `frontend/public/anomira-logo.svg`
- Optional raster/logo variant: `frontend/public/anomira-logo.jpg`
- Browser tab icon: `frontend/public/anomira-logo.svg` (same as navigation logo)

## Tech Stack
- Frontend: React + Vite + Tailwind CSS + Recharts
- Backend: FastAPI
- Data/ML: pandas, numpy, scikit-learn, openpyxl
- Report: Downloadable HTML report

## Project Structure

```text
anomira/
  backend/
    app/
      main.py
      routes/
        data_routes.py
      services/
        anomaly_service.py
        data_store.py
        file_service.py
        profile_service.py
        recommendation_service.py
        report_service.py
      schemas/
        data_schemas.py
      utils/
        serialization.py
    requirements.txt
  frontend/
    public/
      favicon.svg
      anomira-logo.svg
      anomira-logo.jpg
    src/
      components/
      pages/
      services/
      assets/
      App.jsx
      main.jsx
    package.json
    tailwind.config.js
    index.html
  README.md
```

## Backend Setup (FastAPI)

From `anomira/backend`:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend endpoints:
- `GET /api/capabilities`
- `POST /api/upload`
- `POST /api/upload-url` (cloud URL ingestion for large datasets)
- `POST /api/jobs/analyze-url` (TB-ready async cloud URL analyze job)
- `GET /api/jobs/{job_id}` (job status/progress/result polling)
- `POST /api/profile`
- `POST /api/anomalies`
- `POST /api/analyze` (fast one-shot profile + anomalies + recommendations)
- `POST /api/report`

Health check:
- `GET /health`

Optional unbounded-size mode (practically unlimited file-size caps):
- Set `ANOMIRA_MAX_UPLOAD_MB=0` (or negative) to disable local upload size cap.
- Set `ANOMIRA_MAX_CLOUD_DOWNLOAD_MB=0` (or negative) to disable cloud download size cap.
- Note: processing still depends on available CPU/RAM/disk and execution time.

Default capacity configuration:
- Local upload cap defaults to **8 GB** (`ANOMIRA_MAX_UPLOAD_MB=8192`).
- Cloud URL download cap defaults to **8 GB** (`ANOMIRA_MAX_CLOUD_DOWNLOAD_MB=8192`).
- Model execution defaults to stable single-core (`ANOMIRA_MODEL_JOBS=1`). Set `ANOMIRA_MODEL_JOBS=-1` (or a positive core count) to use higher compute parallelism.
- TB-ready chunked mode trigger defaults to **512 MB** (`ANOMIRA_TB_MODE_TRIGGER_MB=512`) for cloud URL async jobs.

## Frontend Setup (React + Vite)

From `anomira/frontend`:

```bash
npm install
npm run dev
```

Frontend dev server runs on `http://localhost:5173` and proxies `/api` to `http://127.0.0.1:8000`.

## Core Features Implemented

1. Dataset upload and validation
- Supports `.csv`, `.tsv`, `.txt`, `.xlsx`, `.json`, and `.jsonl`
- Safe pandas parsing
- Upload capacity endpoint (`/api/capabilities`) exposes max local upload size, max cloud-download size, and supported formats/protocols
- Streamed temp-file ingestion for large files (avoids loading full upload bytes into memory)
- Cloud URL ingestion via `POST /api/upload-url` for HTTPS/HTTP signed URLs
- TB-ready asynchronous cloud URL analysis via `POST /api/jobs/analyze-url` + `GET /api/jobs/{job_id}` polling
- Returns rows, columns, column names, preview rows

2. Data profiling
- Column type detection: numeric, categorical, date, text, id-like
- Missing values, duplicates, constants, high-cardinality columns
- Invalid dates, skewed numeric columns, IQR outlier counts
- GIS profiling: latitude/longitude detection, geometry-column detection, coordinate validity checks, and spatial bounding box summary
- Column health status table with detected issues

3. Anomaly detection
- IQR
- z-score
- Isolation Forest
- Local Outlier Factor
- Automatic anomaly type classification:
  - Point anomalies / global outliers
  - Contextual anomalies
  - Collective anomalies
  - Time-series anomalies:
    - spikes
    - dips
    - trend changes
    - seasonal breaks
  - High-dimensional / multivariate anomalies
  - Geospatial anomalies (location outliers relative to geographic center)
  - Data quality anomalies:
    - missing values
    - duplicates
    - impossible values
    - inconsistent categories
    - extreme skew
    - invalid dates
    - invalid GIS coordinates
- Combined anomaly score and severity levels (`low`, `medium`, `high`, `critical`)
- Suspicious record explanation, affected columns, and recommended action
- Grouped anomaly categorization for comprehension:
  - Point / global
  - Contextual
  - Collective
  - Time-series
  - High-dimensional / multivariate
  - Geospatial
  - Data quality
- Anomaly type breakdown chart + time-series event table + data-quality anomaly panel
- Large-row optimization mode for anomaly models
- TB-ready chunked sampled mode for very large text datasets (`csv/tsv/txt/jsonl`) with explicit `analysis_metadata` in responses

4. Data cleaning recommendations
- Generated from profiling and anomaly outputs
- Prioritized action list for missingness, duplicates, outliers, invalid dates, and more
- Structured auto-fix plan with:
  - `issue`
  - `columns`
  - `recommended_action`
  - `auto_fix_safe`
  - `expected_impact`

5. Branded dashboard UI
- Light premium SaaS style with glassmorphism and clean gradient atmosphere
- Logo shown in sidebar/header
- Upload card, summary cards, data preview table
- Real-time upload progress bar
- Upload capacity and supported file-format display
- Cloud URL input for remote big-data ingestion
- Dataset switcher to upload different data and revisit previous analyzed datasets
- Smoothed upload progress transitions for clearer upload state feedback
- Column health table
- GIS summary panel
- Missing values chart
- Severity cards and anomaly score chart
- Suspicious records table
- Recommendations panel
- Generate report button

6. Downloadable report
- `POST /api/report` returns downloadable HTML
- Includes Anomira branding/logo, summary metrics, severity breakdown, anomaly-type breakdown, data-quality anomalies, GIS summary, time-series events, recommendations, and top suspicious records

## Usage Flow

1. Upload a supported local file format in the dashboard, or provide a cloud URL in the **Cloud Dataset URL** field.
2. For local files, app runs one-click quick analysis (`/api/analyze`) after ingestion.
3. For large cloud URLs, app starts a TB-ready async job and polls progress until complete.
4. Track upload/download + analysis completion states, then review quality issues, GIS summary, anomaly charts, suspicious rows, and recommended fixes.
5. Use the dataset switcher to compare different uploaded datasets.
6. Click **Generate HTML Report** to download a branded report.

Optional:
- Pass `expected_columns` in `/api/analyze`, `/api/anomalies`, or `/api/report` payload to flag missing required variables.

## Known Limitations

1. Processed dataframes and analysis caches are kept in memory for this MVP (no persistent database yet), while raw files are staged via temp files.
2. First analysis run on very large datasets can still take noticeable time; subsequent runs are cached for faster responses.
3. TB-ready chunked mode currently targets `csv/tsv/txt/jsonl`; large `xlsx`/single JSON object files still require full in-memory mode.
4. Cloud URL ingestion currently supports HTTP/HTTPS links and signed object URLs; native `s3://`, `gs://`, and `azure://` URI schemes are not yet direct.
5. GIS geometry parsing is heuristic (WKT-like detection) and does not yet include full topology validation.
6. Time-series anomaly coverage depends on a detectable date/time column and enough chronological depth.
7. Report is HTML-only in this MVP (no PDF export yet).
