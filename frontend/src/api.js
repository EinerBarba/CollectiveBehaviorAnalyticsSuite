const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

let token = null;
let refreshTimer = null;
let refreshPromise = null;
let onSessionExpired = null;

export const setToken = (value) => { token = value; };
export const setSessionExpiredCallback = (cb) => { onSessionExpired = cb; };

export function tokenExpiresIn(jwt) {
  try {
    const payload = JSON.parse(atob(jwt.split(".")[1]));
    return Math.max(0, payload.exp - Math.floor(Date.now() / 1000));
  } catch {
    return 0;
  }
}

export function scheduleRefresh(expiresInSeconds) {
  if (refreshTimer) clearTimeout(refreshTimer);
  const delay = Math.max(10_000, expiresInSeconds * 0.8 * 1000);
  refreshTimer = setTimeout(() => doRefresh().catch(() => {}), delay);
}

export function cancelRefresh() {
  if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
}

function doRefresh() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const resp = await fetch(BASE + "/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!resp.ok) { onSessionExpired?.(); return null; }
      const auth = await resp.json();
      token = auth.access_token;
      try {
        const saved = sessionStorage.getItem("cba-session");
        if (saved) {
          const s = JSON.parse(saved);
          s.token = auth.access_token;
          sessionStorage.setItem("cba-session", JSON.stringify(s));
        }
      } catch {}
      scheduleRefresh(auth.expires_in);
      return auth;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function request(path, { method = "GET", json, form, blob = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }

  let response = await fetch(BASE + path, { method, headers, body, credentials: "include" });

  if (response.status === 401) {
    const refreshed = await doRefresh();
    if (refreshed) {
      headers.Authorization = `Bearer ${token}`;
      response = await fetch(BASE + path, { method, headers, body, credentials: "include" });
    }
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {}
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) return null;
  return blob ? response.blob() : response.json();
}

// Auth
export const login = (email, password) => request("/auth/login", { method: "POST", json: { email, password } });
export const register = (email, full_name, password) =>
  request("/auth/register", { method: "POST", json: { email, full_name, password } });

// User
export const getMe = () => request("/auth/me");

// Laboratories
export const listLaboratories = () => request("/laboratories");
export const createLaboratory = (name) => request("/laboratories", { method: "POST", json: { name } });

// Experiments
export const listExperiments = (laboratory_id) =>
  request(laboratory_id ? `/experiments?laboratory_id=${laboratory_id}` : "/experiments");
export const createExperiment = (laboratory_id, title) =>
  request("/experiments", { method: "POST", json: { laboratory_id, title } });

// Files
export const listFiles = (experiment_id) => request(`/files?experiment_id=${experiment_id}&file_type=video`);
export const listFileVersions = (file_id) => request(`/file-versions?file_id=${file_id}`);

// Processing runs
export const listExperimentRuns = (experiment_id, file_version_id = null) =>
  request(`/processing-runs/by-experiment/${experiment_id}${file_version_id ? `?file_version_id=${file_version_id}` : ""}`);
export const listOutputs = (run_id) =>
  request(`/processing-run-outputs?processing_run_id=${run_id}`);
export const listDatasetFiles = (dataset_version_id) =>
  request(`/dataset-files?dataset_version_id=${dataset_version_id}`);

// Video
export async function uploadVideo(experimentId, file) {
  const form = new FormData();
  form.append("experiment_id", experimentId);
  form.append("upload", file);
  const result = await request("/videos/upload", { method: "POST", form });
  return result.file_version.id;
}

export const getVideoMetadata = (fileVersionId) => request(`/videos/${fileVersionId}/metadata`);
export const getVideoFrame = (fileVersionId, frameIndex) =>
  request(`/videos/${fileVersionId}/frame?frame_index=${frameIndex}`, { blob: true });
export const getDetectionAnalysis = (fileVersionId, frameIndex, params, plate = null) => {
  const { minArea, maxArea, brightnessRatio, minSolidity, minAspectRatio, maxAspectRatio, minCircularity } = params;
  let url = `/videos/${fileVersionId}/detection-analysis?frame_index=${frameIndex}`
    + `&min_area=${minArea}&max_area=${maxArea}&brightness_ratio=${brightnessRatio}`
    + `&min_solidity=${minSolidity}&min_aspect_ratio=${minAspectRatio}&max_aspect_ratio=${maxAspectRatio}&min_circularity=${minCircularity}`;
  if (plate) url += `&plate_cx=${plate.cx}&plate_cy=${plate.cy}&plate_r=${plate.r}`;
  return request(url);
};

// Processing runs
export const startRun = (name, body) => request(`/processing-runs/${name}`, { method: "POST", json: body });
export const startExperimentCB = (experimentId, { fps = null, frameStep = null, windowSize = null, windowStep = null } = {}) =>
  request("/processing-runs/collective-behavior-experiment", {
    method: "POST",
    json: {
      experiment_id: experimentId,
      ...(fps ? { fps } : {}),
      ...(frameStep && frameStep > 1 ? { frame_step: frameStep } : {}),
      ...(windowSize ? { window_size: windowSize } : {}),
      ...(windowStep ? { window_step: windowStep } : {}),
    },
  });
export const getRun = (runId) => request(`/processing-runs/${runId}`);
export const listAccessibleRuns = () => request("/processing-runs/accessible");

export const getRunProgress = (runId) =>
  request(`/processing-runs/${runId}/progress`).catch(() => ({ done: 0, total: 0 }));

// Run status. Resolves with the run, rejects with its error message.
export async function waitForRun(runId, intervalMs = 2000) {
  for (;;) {
    const run = await request(`/processing-runs/${runId}`);
    if (run.status === "succeeded") return run;
    if (run.status === "failed" || run.status === "cancelled") {
      throw new Error(run.error_message || `Run ${run.status}`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

// Like waitForRun but calls onProgress(done, total) on each poll.
export async function waitForRunWithProgress(runId, onProgress, intervalMs = 750) {
  for (;;) {
    const [run, prog] = await Promise.all([
      request(`/processing-runs/${runId}`),
      getRunProgress(runId),
    ]);
    if (onProgress) onProgress(prog.done, prog.total);
    if (run.status === "succeeded") return run;
    if (run.status === "failed" || run.status === "cancelled") {
      throw new Error(run.error_message || `Run ${run.status}`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

// Output dataset version. Pass role to select a specific file within the output dataset.
// falls back to "primary" then the first file when the requested role is not found.
export async function runOutputFileVersionId(runId, role = null) {
  const outputs = await request(`/processing-run-outputs?processing_run_id=${runId}`);
  const output = outputs.find((o) => o.dataset_version_id);
  if (!output) throw new Error("The run has no output dataset");
  const files = await request(`/dataset-files?dataset_version_id=${output.dataset_version_id}`);
  const file = role
    ? (files.find((f) => f.role === role) ?? files.find((f) => f.role === "primary") ?? files[0])
    : (files.find((f) => f.role === "primary") ?? files[0]);
  if (!file) throw new Error("The output dataset has no file");
  return file.file_version_id;
}

export const downloadFileVersion = (fileVersionId) =>
  request(`/file-versions/${fileVersionId}/content`, { blob: true });

export const saveTrajectoryEdit = (fileVersionId, csvContent) =>
  request("/trajectories/save-edit", {
    method: "POST",
    json: { file_version_id: fileVersionId, csv_content: csvContent },
  });

export const saveTrajectoryProgress = (fileVersionId, progressJson) =>
  request("/trajectories/save-progress", {
    method: "POST",
    json: { file_version_id: fileVersionId, progress_json: progressJson },
  });

export const generateNextTracks = (body) =>
  request("/trajectories/generate-next", { method: "POST", json: body });

export const listTrajectoryProgress =(fileVersionId) =>
  request(`/trajectories/progress-list?file_version_id=${fileVersionId}`);

export async function importLightCsv(experimentId, fps, files) {
  const form = new FormData();
  form.append("experiment_id", experimentId);
  if (fps != null) form.append("fps", String(fps));
  for (const f of files) form.append("files", f);
  return request("/processing-runs/light-csv-import", { method: "POST", form });
}

export async function importPositionCsv(experimentId, fps, files) {
  const form = new FormData();
  form.append("experiment_id", experimentId);
  if (fps != null) form.append("fps", String(fps));
  for (const f of files) form.append("files", f);
  return request("/processing-runs/csv-import", { method: "POST", form });
}

export const getCbResults = (runId) => request(`/processing-runs/${runId}/cb-results`);

export const getVideoThumbnail = (fileVersionId) =>
  request(`/videos/${fileVersionId}/thumbnail`, { blob: true });

export const generateVideoThumbnail = (fileVersionId) =>
  request(`/videos/${fileVersionId}/thumbnail`, { method: "POST" });

export const deleteVideo = (fileId) =>
  request(`/videos/${fileId}`, { method: "DELETE" });
