import SectionCard from "./SectionCard";

function formatBytes(bytes) {
  if (!bytes || Number.isNaN(bytes)) {
    return "0 MB";
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatCapacity(maxMb) {
  if (maxMb === null || maxMb === undefined) {
    return "Unlimited";
  }
  const safeMb = Number(maxMb || 0);
  if (!safeMb) {
    return "-";
  }
  if (safeMb >= 1024) {
    return `${(safeMb / 1024).toFixed(2)} GB (${safeMb.toLocaleString()} MB)`;
  }
  return `${safeMb.toLocaleString()} MB`;
}

function UploadCard({
  file,
  onFileChange,
  onUpload,
  cloudUrl,
  onCloudUrlChange,
  onUploadFromUrl,
  loading,
  uploadProgress,
  uploadStage,
  activeJob,
  capabilities,
  datasetHistory,
  currentDatasetId,
  onSelectDataset
}) {
  const capabilitiesLoaded = Boolean(capabilities);
  const supportedFormats = capabilities?.supported_formats?.join(", ") || ".csv, .tsv, .txt, .xlsx, .json, .jsonl";
  const acceptFormats = capabilities?.supported_formats?.join(",") || ".csv,.tsv,.txt,.xlsx,.json,.jsonl";
  const maxSizeLabel = capabilitiesLoaded ? formatCapacity(capabilities?.max_upload_size_mb) : "8.00 GB (8,192 MB)";
  const maxCloudSizeLabel = capabilitiesLoaded ? formatCapacity(capabilities?.max_cloud_download_size_mb) : "8.00 GB (8,192 MB)";
  const largeDatasetLabel = capabilities?.large_dataset_threshold_rows
    ? `${capabilities.large_dataset_threshold_rows.toLocaleString()}+ rows`
    : "120,000+ rows";
  const tbReady = Boolean(capabilities?.tb_ready_async_job_enabled);
  const tbTrigger = capabilities?.tb_mode_trigger_mb;
  const tbFormats = (capabilities?.chunked_tb_mode_formats || []).join(", ");
  const selectedFileSize = file ? formatBytes(file.size) : null;
  const safeProgress = Math.max(0, Math.min(100, uploadProgress || 0));

  const actionLabel =
    uploadStage === "uploading" ? `Uploading ${safeProgress}%` : loading ? "Analyzing..." : "Upload & Analyze";

  return (
    <SectionCard
      title="Upload Dataset"
      subtitle="Upload large structured datasets and analyze full records."
      actions={
        <button
          type="button"
          onClick={onUpload}
          disabled={!file || loading}
          className="rounded-xl bg-gradient-to-r from-sky-600 to-cyan-500 px-4 py-2 text-sm font-semibold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {actionLabel}
        </button>
      }
    >
      <div
        className={`mb-4 grid gap-3 transition-all duration-500 md:grid-cols-3 ${
          capabilitiesLoaded ? "translate-y-0 opacity-100" : "translate-y-1 opacity-80"
        }`}
      >
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Supported Formats</p>
          <p className="mt-1 text-sm text-slate-700">{supportedFormats}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Max Capacity</p>
          <p className="mt-1 text-sm font-semibold text-sky-700">{maxSizeLabel}</p>
          <p className="mt-1 text-xs text-slate-500">Large dataset mode: {largeDatasetLabel}</p>
          {!capabilitiesLoaded ? <p className="mt-1 text-xs text-slate-400">Loading server limits...</p> : null}
        </div>
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Cloud URL Capacity</p>
          <p className="mt-1 text-sm font-semibold text-sky-700">{maxCloudSizeLabel}</p>
          <p className="mt-1 text-xs text-slate-500">Supports HTTPS/HTTP signed dataset URLs</p>
          <p className="mt-1 text-xs text-slate-500">GIS-aware quality checks included</p>
          {tbReady ? (
            <p className="mt-1 text-xs text-slate-500">
              TB-ready async mode: {tbTrigger ? `${tbTrigger}MB+` : "enabled"} ({tbFormats || ".csv, .tsv, .txt, .jsonl"})
            </p>
          ) : null}
        </div>
      </div>

      <label className="block cursor-pointer rounded-2xl border border-dashed border-sky-200 bg-sky-50/70 p-6 text-center transition hover:border-sky-300 hover:bg-sky-100/70">
        <input
          type="file"
          accept={acceptFormats}
          className="hidden"
          onChange={(event) => onFileChange(event.target.files?.[0] || null)}
        />
        <p className="font-display text-sm text-slate-700">Drop file here or click to browse</p>
        <p className="mt-2 text-xs text-slate-500">Fast analysis for structured datasets</p>
        {file ? (
          <p className="mt-3 text-sm text-sky-700">
            Selected: {file.name} ({selectedFileSize})
          </p>
        ) : null}
      </label>

      <div className="mt-4 rounded-xl border border-slate-200 bg-white/75 p-3">
        <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Cloud Dataset URL</p>
        <div className="flex flex-col gap-2 md:flex-row">
          <input
            type="url"
            value={cloudUrl || ""}
            onChange={(event) => onCloudUrlChange(event.target.value)}
            placeholder="https://.../dataset.csv (or signed cloud URL)"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-sky-400"
          />
          <button
            type="button"
            onClick={onUploadFromUrl}
            disabled={loading || !(cloudUrl || "").trim()}
            className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-800 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-45"
          >
            Analyze URL
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Use this for very large files stored in cloud object storage.
        </p>
      </div>

      {(uploadStage === "uploading" || uploadStage === "downloading" || uploadStage === "job_running" || loading) && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white/75 p-3">
          <div className="mb-2 flex items-center justify-between text-xs text-slate-600">
            <span>
              {uploadStage === "uploading"
                ? "Uploading file"
                : uploadStage === "downloading"
                  ? "Downloading cloud dataset"
                  : uploadStage === "job_running"
                    ? `TB-ready async job: ${activeJob?.stage || "running"}`
                  : "Running full-data analysis"}
            </span>
            <span>{uploadStage === "uploading" || uploadStage === "job_running" ? `${safeProgress}%` : "Please wait..."}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className={`h-full rounded-full bg-gradient-to-r from-sky-500 to-cyan-400 transition-all duration-500 ${
                uploadStage === "analyzing" || uploadStage === "downloading" || uploadStage === "job_running"
                  ? "animate-pulse"
                  : ""
              }`}
              style={{ width: `${uploadStage === "uploading" || uploadStage === "job_running" ? safeProgress : 100}%` }}
            />
          </div>
          {uploadStage === "job_running" && activeJob?.message ? (
            <p className="mt-2 text-xs text-slate-600">{activeJob.message}</p>
          ) : null}
        </div>
      )}

      {datasetHistory?.length ? (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white/75 p-3">
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Switch Dataset</p>
          <select
            value={currentDatasetId || ""}
            onChange={(event) => onSelectDataset(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-sky-400"
          >
            {datasetHistory.map((item) => (
              <option key={item.dataset.dataset_id} value={item.dataset.dataset_id}>
                {item.dataset.filename} ({item.dataset.row_count.toLocaleString()} rows)
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs text-slate-500">Upload different data anytime and switch between analyzed datasets.</p>
        </div>
      ) : null}
    </SectionCard>
  );
}

export default UploadCard;
