import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 600000
});

export async function uploadDataset(file) {
  const formData = new FormData();
  formData.append("file", file);

  const { data } = await api.post("/api/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

export async function uploadDatasetWithProgress(file, onProgress) {
  const formData = new FormData();
  formData.append("file", file);

  const { data } = await api.post("/api/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      const total = event.total || 0;
      const loaded = event.loaded || 0;
      if (total > 0 && typeof onProgress === "function") {
        onProgress(Math.min(100, Math.round((loaded / total) * 100)));
      }
    }
  });
  return data;
}

export async function uploadDatasetFromUrl(url, filename = null) {
  const payload = { url };
  if (filename) {
    payload.filename = filename;
  }
  const { data } = await api.post("/api/upload-url", payload);
  return data;
}

export async function startAnalyzeUrlJob(url, filename = null) {
  const payload = { url };
  if (filename) {
    payload.filename = filename;
  }
  const { data } = await api.post("/api/jobs/analyze-url", payload);
  return data;
}

export async function getJobStatus(jobId) {
  const { data } = await api.get(`/api/jobs/${jobId}`);
  return data;
}

export async function getUploadCapabilities() {
  const { data } = await api.get("/api/capabilities");
  return data;
}

export async function profileDataset(datasetId) {
  const { data } = await api.post("/api/profile", { dataset_id: datasetId });
  return data;
}

export async function detectAnomalies(datasetId) {
  const { data } = await api.post("/api/anomalies", { dataset_id: datasetId, top_n: 100 });
  return data;
}

export async function analyzeDataset(datasetId) {
  const { data } = await api.post("/api/analyze", { dataset_id: datasetId, top_n: 100 });
  return data;
}

export async function downloadReport(datasetId) {
  const response = await api.post(
    "/api/report",
    { dataset_id: datasetId, top_n: 100 },
    { responseType: "blob" }
  );

  const blob = new Blob([response.data], { type: "text/html" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "anomira-report.html";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export default api;
