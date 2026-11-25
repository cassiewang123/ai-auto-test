import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig,
} from 'axios';

interface ErrorPayload {
  message?: string;
  // FastAPI 校验错误时 detail 是数组（每条含 loc/msg/type）
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }> | Record<string, unknown>;
}

export function formatDetail(detail: ErrorPayload['detail']): string | null {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // 把 Pydantic 校验错误渲染成可读文本，避免出现 "[object Object]"
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        const field = Array.isArray(item?.loc)
          ? item.loc.filter((part) => part !== 'body' && part !== 'query').join('.')
          : '';
        const msg = item?.msg || '';
        return field && msg ? `${field}: ${msg}` : msg;
      })
      .filter(Boolean);
    return messages.length > 0 ? messages.join('；') : null;
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return null;
  }
}

function extractErrorMessage(error: AxiosError<ErrorPayload>): string {
  return (
    error.response?.data?.message ||
    formatDetail(error.response?.data?.detail) ||
    error.message ||
    '请求失败'
  );
}

function attachCommonHeaders(
  config: InternalAxiosRequestConfig
): InternalAxiosRequestConfig {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  config.headers['X-Request-ID'] =
    crypto.randomUUID?.() || Math.random().toString(36);
  return config;
}

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use(attachCommonHeaders);
apiClient.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError<ErrorPayload>) => {
    const status = error.response?.status;
    if (status === 401) {
      localStorage.removeItem('access_token');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(new Error('登录已过期，请重新登录'));
    }
    if (status === 403) {
      return Promise.reject(new Error(extractErrorMessage(error)));
    }
    if (status === 429) {
      return Promise.reject(new Error('请求过于频繁，请稍后重试'));
    }
    return Promise.reject(new Error(extractErrorMessage(error)));
  }
);

export const authClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

authClient.interceptors.request.use(attachCommonHeaders);
authClient.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError<ErrorPayload>) =>
    Promise.reject(new Error(extractErrorMessage(error)))
);
