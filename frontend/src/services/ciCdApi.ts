import axios from 'axios';
import type { ApiResponse } from '../types';

// CI/CD 集成模块专用 API 客户端（api.ts 为共享文件不可修改，故独立维护实例）
const ciApi = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

ciApi.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.message || error.message || '请求失败';
    return Promise.reject(new Error(msg));
  }
);

// ========== 类型 ==========
export interface ApiToken {
  id: string;
  name: string;
  token_masked: string;
  scopes: string[];
  is_active: boolean;
  expires_at?: string | null;
  last_used_at?: string | null;
  created_at?: string | null;
}

export interface ApiTokenCreateResult extends ApiToken {
  token: string; // 明文 token，仅创建时返回
}

export interface ApiTokenCreate {
  name: string;
  scopes: string[];
  expires_at?: string | null;
}

export interface WebhookConfig {
  id: string;
  name: string;
  url: string;
  has_url: boolean;
  events: string[];
  has_secret: boolean;
  is_active: boolean;
  project_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WebhookConfigCreate {
  name: string;
  url: string;
  events: string[];
  secret?: string;
  is_active?: boolean;
  project_id?: string | null;
}

export interface WebhookConfigUpdate {
  name?: string;
  url?: string;
  events?: string[];
  secret?: string;
  is_active?: boolean;
  project_id?: string | null;
}

export interface CiTriggerResult {
  run_id: string;
  status: string;
  message: string;
  total: number;
  passed: number;
  failed: number;
  error: number;
}

export interface RunStatus {
  run_id: string;
  status: string;
  total: number;
  passed: number;
  failed: number;
  error: number;
  skipped: number;
  duration: number;
  source: string;
  created_at?: string | null;
}

export interface CiTriggerRequest {
  plan_id?: string;
  case_ids?: string[];
  environment_id?: string | null;
}

// 可选 scope
export const TOKEN_SCOPES = [
  'test-cases:execute',
  'test-plans:execute',
  'ci:trigger',
];

// webhook 可选事件
export const WEBHOOK_EVENTS = [
  'test_run.completed',
  'test_run.failed',
  'ping',
];

// ========== API Token ==========
export const apiTokenApi = {
  list: () => ciApi.get<unknown, ApiResponse<ApiToken[]>>('/api-tokens'),
  create: (data: ApiTokenCreate) =>
    ciApi.post<unknown, ApiResponse<ApiTokenCreateResult>>('/api-tokens', data),
  delete: (id: string) =>
    ciApi.delete<unknown, ApiResponse<null>>(`/api-tokens/${id}`),
};

// ========== CI/CD 触发 + Webhook ==========
export const ciCdApi = {
  trigger: (data: CiTriggerRequest) =>
    ciApi.post<unknown, ApiResponse<CiTriggerResult>>('/ci/trigger', data),
  getRunStatus: (runId: string) =>
    ciApi.get<unknown, ApiResponse<RunStatus>>(`/ci/runs/${runId}/status`),
  // Webhook
  listWebhooks: () =>
    ciApi.get<unknown, ApiResponse<WebhookConfig[]>>('/ci/webhooks'),
  createWebhook: (data: WebhookConfigCreate) =>
    ciApi.post<unknown, ApiResponse<WebhookConfig>>('/ci/webhooks', data),
  updateWebhook: (id: string, data: WebhookConfigUpdate) =>
    ciApi.put<unknown, ApiResponse<WebhookConfig>>(`/ci/webhooks/${id}`, data),
  deleteWebhook: (id: string) =>
    ciApi.delete<unknown, ApiResponse<null>>(`/ci/webhooks/${id}`),
  testWebhook: (id: string) =>
    ciApi.post<unknown, ApiResponse<{ webhook_id: string; sent: boolean; results: any[] }>>(
      `/ci/webhooks/${id}/test`
    ),
};
