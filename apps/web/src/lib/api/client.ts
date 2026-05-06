import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { firebaseAuth } from "@/lib/firebase";
import { type ApiErrorBody, ApiError } from "@/types/api.types";

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// ── Request interceptor — attach fresh Firebase ID token ──────────────────────
apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const user = firebaseAuth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor — retry once on 401, translate errors ───────────────
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // On 401: force-refresh the Firebase token and retry the request once
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const user = firebaseAuth.currentUser;
      if (user) {
        try {
          const freshToken = await user.getIdToken(/* forceRefresh */ true);
          original.headers.Authorization = `Bearer ${freshToken}`;
          return apiClient(original);
        } catch {
          await firebaseAuth.signOut();
          if (typeof window !== "undefined") window.location.href = "/login";
        }
      }
    }

    // Translate backend structured errors into ApiError so callers can pattern-match
    // error_code arrives as errorCode because the server middleware converts all JSON keys
    const body = error.response?.data;
    if (body?.errorCode) {
      throw new ApiError(error.response!.status, body.errorCode, body.detail);
    }

    return Promise.reject(error);
  },
);
