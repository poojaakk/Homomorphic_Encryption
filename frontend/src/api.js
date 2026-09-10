import axios from "axios";

const API = "http://127.0.0.1:8000";

export const getNoise       = ()             => axios.get(`${API}/noise`);
export const getNoiseHistory= ()             => axios.get(`${API}/noise/history`);
export const getStatus      = ()             => axios.get(`${API}/status`);
export const getContext     = ()             => axios.get(`${API}/context`);
export const encrypt        = ()             => axios.get(`${API}/encrypt`);
export const bootstrap      = ()             => axios.get(`${API}/bootstrap`);
export const decrypt        = ()             => axios.get(`${API}/decrypt`);
export const add            = ()             => axios.get(`${API}/compute/add`);
export const multiply       = ()             => axios.get(`${API}/compute/multiply`);
export const getLogs        = (category)     =>
  axios.get(`${API}/logs`, { params: category ? { category } : {} });

export const uploadCsv = (file, column) => {
  const form = new FormData();
  form.append("file", file);
  form.append("column", column);
  return axios.post(`${API}/upload`, form);
};
