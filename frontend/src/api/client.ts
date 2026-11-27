import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { Tokens } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18083/api';

let accessToken: string | null = null;
let refreshToken: string | null = null;
let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

// Load tokens from localStorage on module init
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem('polls_tokens');
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      accessToken = parsed.access;
      refreshToken = parsed.refresh;
    } catch {
      // ignore
    }
  }
}

const saveTokens = (tokens: { access: string; refresh: string }) => {
  accessToken = tokens.access;
  refreshToken = tokens.refresh;
  if (typeof window !== 'undefined') {
    localStorage.setItem('polls_tokens', JSON.stringify(tokens));
  }
};

const clearTokens = () => {
  accessToken = null;
  refreshToken = null;
  if (typeof window !== 'undefined') {
    localStorage.removeItem('polls_tokens');
  }
};

const refreshAccessToken = async (): Promise<string | null> => {
  if (isRefreshing) {
    return refreshPromise!;
  }

  if (!refreshToken) {
    return null;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const response = await axios.post<Tokens>(
        `${API_BASE_URL}/auth/refresh`,
        { refresh: refreshToken },
        { headers: { 'Content-Type': 'application/json' } }
      );
      saveTokens(response.data);
      return response.data.access;
    } catch {
      clearTokens();
      return null;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
};

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor - add auth header
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle 401 with token refresh
let logoutCallback: (() => void) | null = null;

export const setLogoutCallback = (callback: () => void) => {
  logoutCallback = callback;
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const newAccess = await refreshAccessToken();
      if (newAccess) {
        originalRequest.headers.Authorization = `Bearer ${newAccess}`;
        return apiClient(originalRequest);
      }

      // Refresh failed - logout
      clearTokens();
      if (logoutCallback) {
        logoutCallback();
      }
      return Promise.reject(error);
    }

    return Promise.reject(error);
  }
);

export { API_BASE_URL, saveTokens, clearTokens, accessToken as getAccessToken };