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
 * POST /video/process — upload a video file and run the full HE pipeline.
 * @param {File}   file      - video file object from <input type="file">
 * @param {number} noiseStd  - Gaussian noise std-dev  (0 = no noise, default 5)
 * @param {function} onUploadProgress - optional axios progress callback
 */
export const processVideo = (file, noiseStd = 5.0, onUploadProgress) => {
  const form = new FormData();
  form.append("file", file);
  form.append("noise_std", String(noiseStd));
  return axios.post(`${API}/video/process`, form, {
    timeout: 300_000,          // 5-minute timeout for large videos
    onUploadProgress,
  });
};
