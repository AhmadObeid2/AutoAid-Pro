import axios, { AxiosHeaders, type InternalAxiosRequestConfig } from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api",
  timeout: 20000,
  headers: {
    Accept: "application/json",
  },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const headers = AxiosHeaders.from(config.headers);
  const isFormData =
    typeof FormData !== "undefined" && config.data instanceof FormData;

  if (isFormData) {
    // Let browser set multipart/form-data + boundary
    headers.delete("Content-Type");
  } else {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  config.headers = headers; // ✅ correct type now
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail =
      err?.response?.data?.detail ||
      err?.response?.data?.error ||
      err?.response?.data ||
      err.message;

    return Promise.reject(
      new Error(typeof detail === "string" ? detail : JSON.stringify(detail))
    );
  }
);
