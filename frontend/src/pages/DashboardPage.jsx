import { useEffect, useMemo, useState } from "react";
import AnomalyScoreChart from "../components/AnomalyScoreChart";
import AnomalySeverityCards from "../components/AnomalySeverityCards";
import AnomalyCategoryGroups from "../components/AnomalyCategoryGroups";
import AnomalyTypeBreakdownChart from "../components/AnomalyTypeBreakdownChart";
import BrandSidebar from "../components/BrandSidebar";
import ColumnHealthTable from "../components/ColumnHealthTable";
import DataQualityAnomalyPanel from "../components/DataQualityAnomalyPanel";
import DataPreviewTable from "../components/DataPreviewTable";
import GisSummaryPanel from "../components/GisSummaryPanel";
import MissingValuesChart from "../components/MissingValuesChart";
import RecommendationPanel from "../components/RecommendationPanel";
import SummaryCards from "../components/SummaryCards";
import SuspiciousRecordsTable from "../components/SuspiciousRecordsTable";
import TimeSeriesEventsTable from "../components/TimeSeriesEventsTable";
import UploadCard from "../components/UploadCard";
import {
  analyzeDataset,
  downloadReport,
  getJobStatus,
  getUploadCapabilities,
  startAnalyzeUrlJob,
  uploadDatasetWithProgress
} from "../services/api";

const FALLBACK_MAX_UPLOAD_MB = 8192;
const FALLBACK_MAX_UPLOAD_BYTES = FALLBACK_MAX_UPLOAD_MB * 1024 * 1024;
const VERCEL_PAYLOAD_LIMIT_MESSAGE =
  "This file is too large for direct upload on Vercel. Use the Cloud Dataset URL field with a public or signed file URL, or deploy the backend on a service built for larger uploads.";

function DashboardPage() {
  const [file, setFile] = useState(null);
  const [cloudUrl, setCloudUrl] = useState("");
  const [dataset, setDataset] = useState(null);
  const [profile, setProfile] = useState(null);
  const [anomalies, setAnomalies] = useState(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [uploadProgressTarget, setUploadProgressTarget] = useState(0);
  const [uploadProgressDisplay, setUploadProgressDisplay] = useState(0);
  const [uploadStage, setUploadStage] = useState("idle");
  const [capabilities, setCapabilities] = useState(null);
  const [datasetHistory, setDatasetHistory] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const canGenerateReport = Boolean(dataset?.dataset_id && !loadingAnalysis && !loadingReport);

  useEffect(() => {
    if (Math.round(uploadProgressDisplay) === Math.round(uploadProgressTarget)) {
      return;
    }

    const timer = window.setInterval(() => {
      setUploadProgressDisplay((prev) => {
        const diff = uploadProgressTarget - prev;
        if (Math.abs(diff) < 0.6) {
          return uploadProgressTarget;
        }
        const step = Math.max(0.8, Math.abs(diff) * 0.18);
        return prev + Math.sign(diff) * step;
      });
    }, 16);

    return () => window.clearInterval(timer);
  }, [uploadProgressDisplay, uploadProgressTarget]);

  useEffect(() => {
    let active = true;
    getUploadCapabilities()
      .then((data) => {
        if (active) {
          setCapabilities(data);
        }
      })
      .catch(() => {
        if (active) {
          setCapabilities(null);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const headerStatus = useMemo(() => {
    if (uploadStage === "uploading") {
      return `Uploading dataset... ${Math.round(uploadProgressDisplay)}% complete`;
    }
    if (uploadStage === "downloading") {
      return "Downloading dataset from cloud URL...";
    }
    if (uploadStage === "analyzing") {
      return "Analyzing full dataset across profiling and anomaly engines...";
    }
    if (uploadStage === "job_running") {
      const jobMessage = activeJob?.message ? ` ${activeJob.message}` : "";
      return `Running TB-ready async analysis... ${Math.round(uploadProgressDisplay)}% complete.${jobMessage}`;
    }
    if (status) {
      return status;
    }
    return "Upload data, track upload progress, and analyze full records quickly.";
  }, [activeJob?.message, status, uploadProgressDisplay, uploadStage]);

  const handleSelectDataset = (datasetId) => {
    const selected = datasetHistory.find((item) => item.dataset.dataset_id === datasetId);
    if (!selected) {
      return;
    }
    setDataset(selected.dataset);
    setProfile(selected.profile);
    setAnomalies(selected.anomalies);
    setStatus(`Loaded ${selected.dataset.filename} from your analyzed dataset list.`);
    setError("");
  };

  const handleAnalyze = async () => {
    if (!file) {
      setError("Please choose a supported file first.");
      return;
    }

    const capBytes = capabilities?.max_upload_size_bytes;
    const hardLimitBytes = capabilities
      ? (capBytes === null || capBytes === undefined ? null : Number(capBytes))
      : FALLBACK_MAX_UPLOAD_BYTES;
    const maxUploadSizeMb = capabilities?.max_upload_size_mb ?? FALLBACK_MAX_UPLOAD_MB;
    if (hardLimitBytes !== null && file.size > hardLimitBytes) {
      setError(
        `File is too large (${(file.size / (1024 * 1024)).toFixed(2)} MB). Max allowed is ${maxUploadSizeMb} MB.`
      );
      return;
    }

    setError("");
    setStatus("");
    setActiveJob(null);
    setLoadingAnalysis(true);
    setUploadProgressTarget(0);
    setUploadProgressDisplay(0);
    setUploadStage("uploading");

    try {
      const upload = await uploadDatasetWithProgress(file, setUploadProgressTarget);
      setUploadProgressTarget(100);
      setDataset(upload);
      setUploadStage("analyzing");
      const analysis = await analyzeDataset(upload.dataset_id);

      setProfile(analysis.profile);
      setAnomalies(analysis.anomalies);
      setDatasetHistory((prev) => {
        const next = [{ dataset: upload, profile: analysis.profile, anomalies: analysis.anomalies }, ...prev];
        const deduped = next.filter(
          (item, idx, arr) =>
            arr.findIndex((candidate) => candidate.dataset.dataset_id === item.dataset.dataset_id) === idx
        );
        return deduped.slice(0, 20);
      });
      setStatus("Analysis complete. Full dataset processed; review issues, anomalies, and auto-fix plan.");
    } catch (err) {
      const message =
        err?.response?.status === 413
          ? VERCEL_PAYLOAD_LIMIT_MESSAGE
          : err?.response?.data?.detail || err?.message || "Failed to process dataset.";
      setError(message);
    } finally {
      setLoadingAnalysis(false);
      setUploadStage("idle");
      setUploadProgressTarget(0);
      setUploadProgressDisplay(0);
    }
  };

  const handleGenerateReport = async () => {
    if (!dataset?.dataset_id) {
      return;
    }

    setLoadingReport(true);
    setError("");

    try {
      await downloadReport(dataset.dataset_id);
      setStatus("Report downloaded successfully.");
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || "Unable to generate report.";
      setError(message);
    } finally {
      setLoadingReport(false);
    }
  };

  const handleAnalyzeFromUrl = async () => {
    const trimmedUrl = (cloudUrl || "").trim();
    if (!trimmedUrl) {
      setError("Please enter a cloud dataset URL.");
      return;
    }

    setError("");
    setStatus("");
    setLoadingAnalysis(true);
    setActiveJob(null);
    setUploadProgressTarget(0);
    setUploadProgressDisplay(0);
    setUploadStage("job_running");

    try {
      const job = await startAnalyzeUrlJob(trimmedUrl);
      setActiveJob(job);
      setUploadProgressTarget(job.progress || 0);

      const pollDelayMs = 1500;
      const maxPollCount = 3600;
      let snapshot = job;
      for (let attempt = 0; attempt < maxPollCount; attempt += 1) {
        if (attempt > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, pollDelayMs));
        }
        snapshot = await getJobStatus(job.job_id);
        setActiveJob(snapshot);
        setUploadProgressTarget(snapshot.progress || 0);

        if (snapshot.status === "completed") {
          break;
        }
        if (snapshot.status === "failed") {
          throw new Error(snapshot.error || snapshot.message || "Async analysis job failed.");
        }
      }

      if (!snapshot || snapshot.status !== "completed") {
        throw new Error("Timed out waiting for async analysis job to complete.");
      }

      const upload = snapshot.dataset;
      const analysis = snapshot.analysis;
      if (!upload || !analysis) {
        throw new Error("Async job completed without analysis payload.");
      }

      setDataset(upload);
      setProfile(analysis.profile);
      setAnomalies(analysis.anomalies);
      setDatasetHistory((prev) => {
        const next = [{ dataset: upload, profile: analysis.profile, anomalies: analysis.anomalies }, ...prev];
        const deduped = next.filter(
          (item, idx, arr) =>
            arr.findIndex((candidate) => candidate.dataset.dataset_id === item.dataset.dataset_id) === idx
        );
        return deduped.slice(0, 20);
      });
      const mode = analysis?.anomalies?.analysis_metadata?.analysis_mode || snapshot?.metadata?.analysis_mode;
      const isApprox = Boolean(
        analysis?.anomalies?.analysis_metadata?.approximate ?? snapshot?.metadata?.approximate
      );
      const modeLabel = mode === "chunked_sampled" ? "chunked sampled mode" : "full mode";
      setStatus(
        `Cloud dataset analyzed successfully in ${modeLabel}${isApprox ? " (approximate at TB scale)" : ""}.`
      );
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || "Failed to process cloud dataset.";
      setError(message);
    } finally {
      setLoadingAnalysis(false);
      setUploadStage("idle");
      setUploadProgressTarget(0);
      setUploadProgressDisplay(0);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-[1600px] p-5 lg:p-7">
        <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <BrandSidebar dataset={dataset} profile={profile} anomalies={anomalies} />

          <main className="space-y-5">
            <section className="glass-card flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="font-display text-2xl font-semibold text-slate-700">Data</h2>
                <p className="mt-2 text-sm text-slate-600">{headerStatus}</p>
              </div>
              <button
                type="button"
                onClick={handleGenerateReport}
                disabled={!canGenerateReport}
                className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-800 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-45"
              >
                {loadingReport ? "Generating Report..." : "Generate HTML Report"}
              </button>
            </section>

            <UploadCard
              file={file}
              onFileChange={setFile}
              onUpload={handleAnalyze}
              cloudUrl={cloudUrl}
              onCloudUrlChange={setCloudUrl}
              onUploadFromUrl={handleAnalyzeFromUrl}
              loading={loadingAnalysis}
              uploadProgress={Math.round(uploadProgressDisplay)}
              uploadStage={uploadStage}
              activeJob={activeJob}
              capabilities={capabilities}
              datasetHistory={datasetHistory}
              currentDatasetId={dataset?.dataset_id}
              onSelectDataset={handleSelectDataset}
            />

            {error ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>
            ) : null}

            <SummaryCards dataset={dataset} profile={profile} anomalies={anomalies} />

            <div className="grid gap-5 2xl:grid-cols-2">
              <DataPreviewTable rows={dataset?.preview || []} />
              <MissingValuesChart missingValues={profile?.missing_values} />
            </div>

            <ColumnHealthTable columnHealth={profile?.column_health || []} />

            <GisSummaryPanel geospatialSummary={profile?.geospatial_summary || {}} />

            <AnomalySeverityCards anomalies={anomalies} />

            <AnomalyCategoryGroups groups={anomalies?.anomaly_groups || []} />

            <div className="grid gap-5 2xl:grid-cols-2">
              <AnomalyTypeBreakdownChart anomalyTypeBreakdown={anomalies?.anomaly_type_breakdown || {}} />
              <DataQualityAnomalyPanel qualityAnomalies={anomalies?.quality_anomalies || {}} />
            </div>

            <div className="grid gap-5 2xl:grid-cols-2">
              <AnomalyScoreChart distribution={anomalies?.anomaly_score_distribution} />
              <RecommendationPanel
                recommendations={anomalies?.recommendations || []}
                autoFixPlan={anomalies?.auto_fix_plan || []}
              />
            </div>

            <TimeSeriesEventsTable events={anomalies?.time_series_events || []} />

            <SuspiciousRecordsTable records={anomalies?.records || []} />
          </main>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;
