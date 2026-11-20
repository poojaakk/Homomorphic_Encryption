import axios from "axios";

const API = "http://127.0.0.1:8000";

// ── Existing static-mode endpoints (unchanged) ────────────────────────────
export const getNoise        = ()         => axios.get(`${API}/noise`);
export const getNoiseHistory = ()         => axios.get(`${API}/noise/history`);
export const getStatus       = ()         => axios.get(`${API}/status`);
export const getContext      = ()         => axios.get(`${API}/context`);
export const encrypt         = ()         => axios.get(`${API}/encrypt`);
export const bootstrap       = ()         => axios.get(`${API}/bootstrap`);
export const decrypt         = ()         => axios.get(`${API}/decrypt`);
export const add             = ()         => axios.get(`${API}/compute/add`);
export const multiply        = ()         => axios.get(`${API}/compute/multiply`);
export const getLogs         = (category) =>
  axios.get(`${API}/logs`, { params: category ? { category } : {} });

export const uploadCsv = (file, column) => {
  const form = new FormData();
  form.append("file", file);
  form.append("column", column);
  return axios.post(`${API}/upload`, form);
};

// ── Video streaming endpoints ─────────────────────────────────────────────

/** GET /video/status — poll processing state */
export const getVideoStatus = () => axios.get(`${API}/video/status`);

/**
 * POST /video/process — HE stream on every frame (CKKS computation noise).
 */
export const processVideo = (file, onUploadProgress, threshold = 50) => {
  const form = new FormData();
  form.append("file", file);
  form.append("threshold", String(Math.max(10, Math.min(500, threshold))));
  return axios.post(`${API}/video/process`, form, {
    timeout: 1_200_000,
    onUploadProgress,
  });
};

// ── Frame analysis endpoints ──────────────────────────────────────────────

/**
 * POST /frames/analyze — upload video → extract every frame → grayscale stats.
 * Returns FrameAnalysisResponse with full stats list.
 */
export const analyzeFrames = (file, onUploadProgress) => {
  const form = new FormData();
  form.append("file", file);
  return axios.post(`${API}/frames/analyze`, form, {
    timeout: 1_200_000,  // 20 minutes for large videos
    onUploadProgress,
  });
};

/** GET /frames/analyze/status — live progress during processing */
export const getFrameAnalysisStatus = () =>
  axios.get(`${API}/frames/analyze/status`);

/**
 * GET /frames/page — fetch JPEG thumbnail + stat for a single frame.
 * @param {number} frameIdx  Zero-based frame index
 * @param {number} width     Thumbnail width (default 320)
 * @param {number} height    Thumbnail height (default 180)
 */
export const getFramePage = (frameIdx, width = 320, height = 180) =>
  axios.get(`${API}/frames/page`, {
    params: { frame_idx: frameIdx, width, height },
    timeout: 15_000,
  });

/**
 * GET /frames/histogram — grayscale histogram for a single frame.
 * @param {number} frameIdx  Zero-based frame index
 * @param {number} bins      Number of histogram buckets (default 32)
 */
export const getFrameHistogram = (frameIdx, bins = 32) =>
  axios.get(`${API}/frames/histogram`, {
    params: { frame_idx: frameIdx, bins },
    timeout: 15_000,
  });
