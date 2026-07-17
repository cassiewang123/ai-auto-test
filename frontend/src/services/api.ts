import { apiClient } from './http';
import type {
  ApiResponse,
  PageResponse,
  Environment,
  EnvironmentCreate,
  Project,
  ProjectCreate,
  TestCase,
  TestCaseCreate,
  TestPlan,
  TestPlanCreate,
  TestResult,
  TestRunSummary,
  TrendPoint,
  UiTestCase,
  UiElement,
  PerformanceTest,
  PerformanceResult,
  UiTestRecord,
  GlobalVariable,
  GlobalVariableCreate,
  Job,
  JobArtifact,
  JobCreateInput,
  JobEvent,
  JobListParams,
} from '../types';

// 批量操作结果类型
interface BatchExecuteResult {
  total: number;
  passed: number;
  failed: number;
  error: number;
  results: any[];
}

interface BatchDeleteResult {
  total: number;
  deleted: number;
  not_found: number;
}

interface BatchMoveResult {
  total: number;
  moved: number;
  not_found: number;
}

// 统一的 API Client（推荐使用的主实例）
export { apiClient } from './http';

// 兼容别名：内部历史代码使用 `api` 命名
const api = apiClient;

// ========== 环境 ==========
export const environmentApi = {
  list: (params?: { page?: number; page_size?: number; name?: string }) =>
    api.get<unknown, PageResponse<Environment>>('/environments', { params }),
  get: (id: string) =>
    api.get<unknown, ApiResponse<Environment>>(`/environments/${id}`),
  create: (data: EnvironmentCreate) =>
    api.post<unknown, ApiResponse<Environment>>('/environments', data),
  update: (id: string, data: Partial<EnvironmentCreate>) =>
    api.put<unknown, ApiResponse<Environment>>(`/environments/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<Environment>>(`/environments/${id}`),
};

// ========== 测试用例 ==========
export const testCaseApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    group_path?: string;
    project_id?: string;
    url_search?: string;
    title_search?: string;
  }) => api.get<unknown, PageResponse<TestCase>>('/test-cases', { params }),
  get: (id: string) =>
    api.get<unknown, ApiResponse<TestCase>>(`/test-cases/${id}`),
  create: (data: TestCaseCreate) =>
    api.post<unknown, ApiResponse<TestCase>>('/test-cases', data),
  update: (id: string, data: Partial<TestCaseCreate>) =>
    api.put<unknown, ApiResponse<TestCase>>(`/test-cases/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<TestCase>>(`/test-cases/${id}`),
  copy: (id: string) =>
    api.post<unknown, ApiResponse<TestCase>>(`/test-cases/${id}/copy`),
  batchExecute: (caseIds: string[]) =>
    api.post<unknown, ApiResponse<BatchExecuteResult>>('/test-cases/batch-execute', { case_ids: caseIds }),
  batchDelete: (caseIds: string[]) =>
    api.post<unknown, ApiResponse<BatchDeleteResult>>('/test-cases/batch-delete', { case_ids: caseIds }),
  batchMove: (caseIds: string[], projectId: string | null) =>
    api.post<unknown, ApiResponse<BatchMoveResult>>('/test-cases/batch-move', { case_ids: caseIds, project_id: projectId }),
  reorder: (caseIds: string[]) =>
    api.post<unknown, ApiResponse<{ total: number; updated: number }>>('/test-cases/reorder', { case_ids: caseIds }),
  downloadDoc: async (id: string) => {
    const blob = await api.get<unknown, Blob>(`/test-cases/${id}/doc`, {
      responseType: 'blob',
    });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `接口文档_${id.slice(0, 8)}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  },
};

// ========== 测试计划 ==========
export const testPlanApi = {
  list: (params?: { page?: number; page_size?: number; project_id?: string }) =>
    api.get<unknown, PageResponse<TestPlan>>('/test-plans', { params }),
  get: (id: string) =>
    api.get<unknown, ApiResponse<TestPlan>>(`/test-plans/${id}`),
  create: (data: TestPlanCreate) =>
    api.post<unknown, ApiResponse<TestPlan>>('/test-plans', data),
  update: (id: string, data: Partial<TestPlanCreate>) =>
    api.put<unknown, ApiResponse<TestPlan>>(`/test-plans/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<TestPlan>>(`/test-plans/${id}`),
  addItem: (planId: string, data: { test_case_id: string; order: number }) =>
    api.post<unknown, ApiResponse<any>>(`/test-plans/${planId}/items`, data),
  removeItem: (planId: string, caseId: string) =>
    api.delete<unknown, ApiResponse<any>>(`/test-plans/${planId}/items/${caseId}`),
};

// ========== 报告 ==========
export const reportApi = {
  listRunResults: (runId: string, params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<TestResult>>(`/reports/runs/${runId}/results`, {
      params,
    }),
  getRunSummary: (runId: string) =>
    api.get<unknown, ApiResponse<TestRunSummary>>(`/reports/runs/${runId}/summary`),
  getTrends: (start: string, end: string) =>
    api.get<unknown, ApiResponse<TrendPoint[]>>('/reports/trends', {
      params: { start, end },
    }),
  // 最近 N 次执行批次列表
  listRuns: (limit?: number) =>
    api.get<unknown, ApiResponse<any[]>>('/reports/runs', { params: { limit } }),
  // 单次执行详情
  getRunDetail: (runId: string) =>
    api.get<unknown, ApiResponse<any>>(`/reports/runs/${runId}`),
  // 趋势数据
  getTrend: (limit?: number) =>
    api.get<unknown, ApiResponse<any>>('/reports/trend', { params: { limit } }),
};

// ========== 报告导出 ==========
async function downloadReport(runId: string, format: 'html' | 'pdf') {
  const blob = await api.get<unknown, Blob>(
    `/report-export/${runId}/${format}`,
    { responseType: 'blob' }
  );
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = `测试报告_${runId.slice(0, 8)}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export const reportExportApi = {
  exportHtml: (runId: string) => downloadReport(runId, 'html'),
  exportPdf: (runId: string) => downloadReport(runId, 'pdf'),
};

// ========== 接口覆盖率 ==========
export const coverageApi = {
  get: (projectId?: string) =>
    api.get<unknown, ApiResponse<any>>('/coverage', { params: { project_id: projectId } }),
};

// ========== AI ==========
export const aiApi = {
  generateTestCase: (data: { description: string; api_schema?: any }) =>
    api.post<unknown, ApiResponse<{ code: string }>>(
      '/ai/generate-test-case',
      data
    ),
  recommendAssertions: (data: { response_sample: any }) =>
    api.post<unknown, ApiResponse<{ assertions: any[] }>>(
      '/ai/recommend-assertions',
      data
    ),
  analyzeFailure: (data: any) =>
    api.post<unknown, ApiResponse<any>>('/ai/analyze-failure', data),
  // 结构化用例生成（批量，预览不入库）
  generateTestCases: (data: {
    source_type: 'interface' | 'har' | 'description';
    source_data: Record<string, any>;
    options?: Record<string, any>;
  }) =>
    api.post<unknown, ApiResponse<{ cases: any[]; total: number }>>(
      '/ai/generate-test-cases',
      data
    ),
  // 将选中的结构化用例导入用例库
  importCases: (data: { cases: any[]; project_id?: string | null }) =>
    api.post<unknown, ApiResponse<{ created_count: number; case_ids: string[] }>>(
      '/ai/import-cases',
      data
    ),
};

// ========== 执行测试 ==========
export interface PreRequest {
  name: string;
  method: string;
  url: string;
  headers?: Record<string, string>;
  params?: Record<string, any>;
  body?: any;
  extract_rules?: any[];
}

export interface ExecuteRequest {
  method: string;
  url: string;
  headers?: Record<string, string>;
  params?: Record<string, any>;
  body?: any;
  graphql_query?: string;
  assertions?: any[];
  variables?: Record<string, any>;
  timeout?: number;
  pre_requests?: PreRequest[];
  files?: any[];
  cookies?: Array<{ name: string; value: string; path?: string; domain?: string }>;
  pre_script?: string;
  post_script?: string;
  retry_count?: number;
  retry_interval?: number;
}

export interface ExecutionResultData {
  test_case_id: string;
  status: string;
  duration: number;
  request: any;
  response: {
    status_code: number;
    headers: Record<string, string>;
    body: any;
    elapsed: number;
    text: string;
  } | null;
  assertion_results: any[];
  extracted_variables: any[];
  error_message: string | null;
  executed_at: string;
  // 新增字段
  pre_script_result?: { success: boolean; output: string; error: string | null };
  post_script_result?: { success: boolean; output: string; error: string | null };
  retry_attempts?: Array<{ attempt: number; status: string; duration: number; status_code: number | null; error: string | null }>;
  session_cookies?: Array<{ name: string; value: string; path?: string; domain?: string }>;
}

export const executionApi = {
  run: (data: ExecuteRequest) =>
    api.post<unknown, ApiResponse<ExecutionResultData>>('/execution/run', data),
  runMultipart: (
    fields: Omit<ExecuteRequest, 'files'> & { fileList: File[]; fileFields: string[] }
  ) => {
    const formData = new FormData();
    formData.append('method', fields.method);
    formData.append('url', fields.url);
    formData.append('headers', JSON.stringify(fields.headers || {}));
    formData.append('params', JSON.stringify(fields.params || {}));
    formData.append('body', JSON.stringify(fields.body || ''));
    formData.append('assertions', JSON.stringify(fields.assertions || []));
    formData.append('variables', JSON.stringify(fields.variables || {}));
    formData.append('timeout', String(fields.timeout || 30));
    formData.append('pre_requests', JSON.stringify(fields.pre_requests || []));
    formData.append('cookies', JSON.stringify(fields.cookies || []));
    formData.append('pre_script', fields.pre_script || '');
    formData.append('post_script', fields.post_script || '');
    formData.append('retry_count', String(fields.retry_count || 0));
    formData.append('retry_interval', String(fields.retry_interval ?? 1.0));
    fields.fileList.forEach((file, idx) => {
      const fieldName = fields.fileFields[idx] || 'file';
      // 用 field::filename 格式传递字段名
      const renamed = new File([file], `${fieldName}::${file.name}`, {
        type: file.type,
      });
      formData.append('files', renamed);
    });
    return api.post<unknown, ApiResponse<ExecutionResultData>>(
      '/execution/run-multipart',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },
  runSavedCase: (caseId: string) =>
    api.post<unknown, ApiResponse<ExecutionResultData>>(
      `/execution/run/${caseId}`
    ),
};

// ========== 历史调用记录 ==========
export interface CallHistoryRecord {
  id: string;
  record_kind: 'call_history' | 'execution_job';
  deletable: boolean;
  method: string;
  url: string;
  status_code: number | null;
  status: string;
  duration: number;
  has_files: boolean;
  source: string;
  test_case_id: string | null;
  project_id?: string | null;
  error_message: string | null;
  executed_at: string;
  title?: string | null;
  // 详情字段
  headers?: Record<string, string>;
  params?: Record<string, any>;
  body?: any;
  response_headers?: Record<string, string>;
  response_body?: any;
  response_text?: string;
  assertion_results?: any[];
  pre_request_results?: any[];
}

export interface HistoryStats {
  total: number;
  passed: number;
  failed: number;
  error: number;
  skipped: number;
  pass_rate: number;
  avg_duration: number;
}

export const historyApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    method?: string;
    url?: string;
    project_id?: string;
  }) => api.get<unknown, PageResponse<CallHistoryRecord>>('/history', { params }),
  get: (id: string) =>
    api.get<unknown, ApiResponse<CallHistoryRecord>>(`/history/${id}`),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/history/${id}`),
  clear: (projectId?: string) =>
    api.delete<unknown, ApiResponse<any>>('/history', {
      params: projectId ? { project_id: projectId } : undefined,
    }),
  stats: (projectId?: string) =>
    api.get<unknown, ApiResponse<HistoryStats>>('/history/stats', {
      params: projectId ? { project_id: projectId } : undefined,
    }),
};

// ========== 接口导入 ==========
export interface ImportedEndpoint {
  title: string;
  description: string;
  group_path: string;
  markers: string[];
  method: string;
  url: string;
  headers: Record<string, string>;
  params: Record<string, any>;
  body: any;
  assertions: any[];
}

export interface ImportResult {
  total: number;
  created: number;
  case_ids: string[];
  endpoints: ImportedEndpoint[];
  error?: string;
}

export const importApi = {
  preview: (data: { url?: string; spec?: any; base_url?: string; path_prefix?: string }) =>
    api.post<unknown, ApiResponse<{ total: number; endpoints: ImportedEndpoint[]; error?: string }>>(
      '/import/preview',
      data
    ),
  importOpenapi: (data: {
    url?: string;
    spec?: any;
    base_url?: string;
    path_prefix?: string;
    preview_only?: boolean;
  }) => api.post<unknown, ApiResponse<ImportResult>>('/import/openapi', data),
  // HAR 抓包导入：预览解析结果
  previewHar: (data: { har_content: any; domain_filter?: string; method_filter?: string }) =>
    api.post<unknown, ApiResponse<{ total: number; interfaces: any[]; error?: string }>>(
      '/import/har/preview',
      data
    ),
  // HAR 抓包导入：将选中的接口批量创建为 TestCase
  importHar: (data: { selected_interfaces: any[]; project_id?: string }) =>
    api.post<unknown, ApiResponse<{ created_count: number; case_ids: string[] }>>(
      '/import/har/import',
      data
    ),
};

// ========== 项目管理 ==========
export const projectApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<Project>>('/projects', { params }),
  listAll: () =>
    api.get<unknown, ApiResponse<Project[]>>('/projects/all'),
  get: (id: string) =>
    api.get<unknown, ApiResponse<Project>>(`/projects/${id}`),
  create: (data: ProjectCreate) =>
    api.post<unknown, ApiResponse<Project>>('/projects', data),
  update: (id: string, data: Partial<ProjectCreate>) =>
    api.put<unknown, ApiResponse<Project>>(`/projects/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<Project>>(`/projects/${id}`),
  stats: (id: string) =>
    api.get<unknown, ApiResponse<any>>(`/projects/${id}/stats`),
};

// ========== 页面抓取 ==========
export interface CapturedEndpoint {
  method: string;
  url: string;
  title: string;
  group_path: string;
  headers: Record<string, string>;
  params: Record<string, any>;
  body: any;
  source_file: string;
}

export const captureApi = {
  scan: (data: { url: string; base_url?: string }) =>
    api.post<unknown, ApiResponse<{ total: number; endpoints: CapturedEndpoint[]; error?: string }>>('/capture/scan', data),
  import: (data: { project_id: string; base_url?: string; endpoints: any[] }) =>
    api.post<unknown, ApiResponse<{ total: number; created: number; case_ids: string[] }>>('/capture/import', data),
};

// ========== 定时任务 ==========
export const scheduledTaskApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<any>>('/scheduled-tasks', { params }),
  create: (data: any) =>
    api.post<unknown, ApiResponse<any>>('/scheduled-tasks', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/scheduled-tasks/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/scheduled-tasks/${id}`),
  toggle: (id: string) =>
    api.post<unknown, ApiResponse<any>>(`/scheduled-tasks/${id}/toggle`),
  run: (id: string) =>
    api.post<unknown, ApiResponse<any>>(`/scheduled-tasks/${id}/run`),
};

// ========== Mock 服务 ==========
export const mockApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<any>>('/mock-service', { params }),
  create: (data: any) =>
    api.post<unknown, ApiResponse<any>>('/mock-service', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/mock-service/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/mock-service/${id}`),
  toggle: (id: string) =>
    api.post<unknown, ApiResponse<any>>(`/mock-service/${id}/toggle`),
};

// ========== 变更历史 ==========
export const changeLogApi = {
  getByCaseId: (caseId: string) =>
    api.get<unknown, ApiResponse<any[]>>(`/change-logs/${caseId}`),
};

// ========== 数据库断言 ==========
export const dbAssertionApi = {
  list: (testCaseId: string) =>
    api.get<unknown, ApiResponse<any[]>>('/db-assertions', {
      params: { test_case_id: testCaseId },
    }),
  create: (data: any) => api.post<unknown, ApiResponse<any>>('/db-assertions', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/db-assertions/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/db-assertions/${id}`),
  test: (id: string, envId: string, variables?: any) =>
    api.post<unknown, ApiResponse<any>>(
      `/db-assertions/${id}/test`,
      variables || {},
      { params: { env_id: envId } }
    ),
};

// ---------- UI 测试用例 ----------
export const uiTestCaseApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
    title_search?: string;
  }) => api.get<unknown, PageResponse<UiTestCase>>('/ui-test-cases', { params }),
  get: (id: string) => api.get<unknown, ApiResponse<UiTestCase>>(`/ui-test-cases/${id}`),
  create: (data: any) => api.post<unknown, ApiResponse<UiTestCase>>('/ui-test-cases', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<UiTestCase>>(`/ui-test-cases/${id}`, data),
  delete: (id: string) => api.delete<unknown, ApiResponse<any>>(`/ui-test-cases/${id}`),
  run: (id: string) => api.post<unknown, ApiResponse<any>>(`/ui-test-cases/${id}/run`, null, { timeout: 300000 }),
  startRecording: (data: { url: string; browser_type?: string }) =>
    api.post<unknown, ApiResponse<any>>('/ui-test-cases/start-recording', data),
  getRecordingEvents: (sessionId: string) =>
    api.get<unknown, ApiResponse<any>>(`/ui-test-cases/recording/${sessionId}/events`),
  stopRecording: (sessionId: string) =>
    api.post<unknown, ApiResponse<any>>(`/ui-test-cases/stop-recording/${sessionId}`, null, { timeout: 60000 }),
  saveRecording: (sessionId: string, params: { title: string; project_id?: string; url?: string; browser_type?: string }) =>
    api.post<unknown, ApiResponse<any>>(`/ui-test-cases/recording/${sessionId}/save`, null, { params, timeout: 60000 }),
  // 从现有用例提取步骤组（Page Object Model）
  extractSteps: (caseId: string, data: { name: string; description?: string; start_index?: number; end_index?: number | null; project_id?: string }) =>
    api.post<unknown, ApiResponse<any>>(`/ui-test-cases/${caseId}/extract-steps`, data),
};

// ---------- 可复用步骤组（Page Object Model） ----------
export const stepLibraryApi = {
  list: (params?: { page?: number; page_size?: number; project_id?: string; search?: string }) =>
    api.get<unknown, PageResponse<any>>('/step-library', { params }),
  get: (id: string) => api.get<unknown, ApiResponse<any>>(`/step-library/${id}`),
  create: (data: any) => api.post<unknown, ApiResponse<any>>('/step-library', data),
  update: (id: string, data: any) => api.put<unknown, ApiResponse<any>>(`/step-library/${id}`, data),
  delete: (id: string) => api.delete<unknown, ApiResponse<any>>(`/step-library/${id}`),
  duplicate: (id: string) => api.post<unknown, ApiResponse<any>>(`/step-library/${id}/duplicate`),
  // 展开步骤组，返回完整步骤列表（用于预览）
  expand: (id: string) => api.get<unknown, ApiResponse<any>>(`/step-library/${id}/expand`),
};

// ---------- UI 测试执行记录 ----------
export const uiTestRecordApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
    case_id?: string;
    status?: string;
    start_date?: string;
    end_date?: string;
  }) => api.get<unknown, PageResponse<UiTestRecord>>('/ui-test-records', { params }),
  get: (id: string) => api.get<unknown, ApiResponse<UiTestRecord>>(`/ui-test-records/${id}`),
  statsByProject: () => api.get<unknown, ApiResponse<any[]>>('/ui-test-records/stats/by-project'),
  statsTrend: (days?: number) => api.get<unknown, ApiResponse<any>>('/ui-test-records/stats/trend', { params: { days } }),
  searchLogs: (params?: {
    page?: number;
    page_size?: number;
    keyword?: string;
    level?: string;
    project_id?: string;
    start_date?: string;
    end_date?: string;
  }) => api.get<unknown, PageResponse<any>>('/ui-test-records/logs/search', { params }),
};

// ---------- UI 元素对象库 ----------
export const uiElementApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
    name_search?: string;
  }) => api.get<unknown, PageResponse<UiElement>>('/ui-elements', { params }),
  get: (id: string) => api.get<unknown, ApiResponse<UiElement>>(`/ui-elements/${id}`),
  create: (data: any) => api.post<unknown, ApiResponse<UiElement>>('/ui-elements', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<UiElement>>(`/ui-elements/${id}`, data),
  delete: (id: string) => api.delete<unknown, ApiResponse<any>>(`/ui-elements/${id}`),
};

// ---------- UI 测试套件 ----------
export const uiTestSuiteApi = {
  list: (params?: { page?: number; page_size?: number; project_id?: string }) =>
    api.get<unknown, PageResponse<any>>('/ui-test-suites', { params }),
  get: (id: string) => api.get<unknown, ApiResponse<any>>(`/ui-test-suites/${id}`),
  create: (data: any) => api.post<unknown, ApiResponse<any>>('/ui-test-suites', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/ui-test-suites/${id}`, data),
  delete: (id: string) => api.delete<unknown, ApiResponse<any>>(`/ui-test-suites/${id}`),
  run: (id: string) =>
    api.post<unknown, ApiResponse<any>>(`/ui-test-suites/${id}/run`, null, { timeout: 600000 }),
  listRuns: (suiteId: string) =>
    api.get<unknown, ApiResponse<any[]>>(`/ui-test-suites/${suiteId}/runs`),
  getRun: (runId: string) => api.get<unknown, ApiResponse<any>>(`/ui-test-suites/runs/${runId}`),
};

// ---------- 视觉回归 ----------
export const visualRegressionApi = {
  listBaselines: (params?: { page?: number; page_size?: number; case_id?: string }) =>
    api.get<unknown, PageResponse<any>>('/visual-regression/baselines', { params }),
  createBaseline: (data: {
    ui_test_case_id: string;
    name: string;
    baseline_image: string;
    threshold?: number;
    screenshot_path?: string;
  }) => api.post<unknown, ApiResponse<any>>('/visual-regression/baselines', data),
  updateBaseline: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/visual-regression/baselines/${id}`, data),
  deleteBaseline: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/visual-regression/baselines/${id}`),
  listDiffs: (params: { record_id?: string; baseline_id?: string }) =>
    api.get<unknown, ApiResponse<any[]>>('/visual-regression/diffs', { params }),
};

// ---------- UI JUnit XML 导出 ----------
export const uiJunitApi = {
  // 单条执行记录的 JUnit XML
  getRecordJunit: (recordId: string) =>
    api.get<unknown, string>(`/ui-test-records/${recordId}/junit`, {
      responseType: 'text',
      transformResponse: [(data) => data],
    }),
  // 套件执行的 JUnit XML
  getSuiteRunJunit: (runId: string) =>
    api.get<unknown, string>(`/ui-test-suites/runs/${runId}/junit`, {
      responseType: 'text',
      transformResponse: [(data) => data],
    }),
};

// ---------- 性能测试 ----------
export const performanceTestApi = {
  list: (params?: { page?: number; page_size?: number; project_id?: string }) =>
    api.get<unknown, PageResponse<PerformanceTest>>('/perf-tests', { params }),
  get: (id: string) => api.get<unknown, ApiResponse<PerformanceTest>>(`/perf-tests/${id}`),
  create: (data: any) => api.post<unknown, ApiResponse<PerformanceTest>>('/perf-tests', data),
  update: (id: string, data: any) =>
    api.put<unknown, ApiResponse<PerformanceTest>>(`/perf-tests/${id}`, data),
  delete: (id: string) => api.delete<unknown, ApiResponse<any>>(`/perf-tests/${id}`),
  // 异步启动压测，返回 { test_id, run_id, status: 'running' }
  run: (id: string) => api.post<unknown, ApiResponse<any>>(`/perf-tests/${id}/run`),
  getResults: (testId: string, params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<PerformanceResult>>(`/perf-tests/${testId}/results`, {
      params,
    }),
  listAllResults: (params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<PerformanceResult>>('/perf-tests/results', {
      params,
    }),
  // 功能17：实时指标轮询
  getRealtime: (testId: string) =>
    api.get<unknown, ApiResponse<any>>(`/perf-tests/${testId}/realtime`),
  clearRealtime: (testId: string) =>
    api.delete<unknown, ApiResponse<any>>(`/perf-tests/${testId}/realtime`),
  // 功能15：服务器监控指标时间序列
  getMetrics: (testId: string, resultId?: string) =>
    api.get<unknown, ApiResponse<any>>(`/perf-tests/${testId}/metrics`, {
      params: resultId ? { result_id: resultId } : undefined,
    }),
  // 功能16：SLA 评估详情
  getSla: (testId: string, resultId: string) =>
    api.get<unknown, ApiResponse<any>>(`/perf-tests/${testId}/results/${resultId}/sla`),
  // 功能18：趋势对比
  getTrends: (testIds: string[], metric: string) =>
    api.get<unknown, ApiResponse<any>>('/perf-tests/trends', {
      params: { test_ids: testIds.join(','), metric },
    }),
  // 功能18：同场景历史结果
  getHistory: (testId: string, params?: { page?: number; page_size?: number }) =>
    api.get<unknown, PageResponse<PerformanceResult>>(`/perf-tests/${testId}/history`, {
      params,
    }),
};

// ---------- 知识工程 ----------
export const knowledgeApi = {
  // 缺陷模式
  listDefects: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
    pattern_type?: string;
  }) => api.get<unknown, PageResponse<any>>('/knowledge/defects', { params }),
  createDefect: (data: any) =>
    api.post<unknown, ApiResponse<any>>('/knowledge/defects', data),
  extractDefect: (testResultId: string) =>
    api.post<unknown, ApiResponse<any>>(
      '/knowledge/defects/extract',
      null,
      { params: { test_result_id: testResultId } }
    ),
  updateDefect: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/knowledge/defects/${id}`, data),
  deleteDefect: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/knowledge/defects/${id}`),

  // 业务规则
  listRules: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
    rule_type?: string;
  }) => api.get<unknown, PageResponse<any>>('/knowledge/rules', { params }),
  createRule: (data: any) =>
    api.post<unknown, ApiResponse<any>>('/knowledge/rules', data),
  promoteRules: (threshold?: number) =>
    api.post<unknown, ApiResponse<any>>(
      '/knowledge/rules/promote',
      null,
      { params: { threshold } }
    ),
  updateRule: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/knowledge/rules/${id}`, data),
  deleteRule: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/knowledge/rules/${id}`),

  // 接口知识
  listInterfaces: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
  }) => api.get<unknown, PageResponse<any>>('/knowledge/interfaces', { params }),
  createInterface: (data: any) =>
    api.post<unknown, ApiResponse<any>>('/knowledge/interfaces', data),
  updateInterface: (id: string, data: any) =>
    api.put<unknown, ApiResponse<any>>(`/knowledge/interfaces/${id}`, data),
  deleteInterface: (id: string) =>
    api.delete<unknown, ApiResponse<any>>(`/knowledge/interfaces/${id}`),

  // RAG 检索
  search: (query: string, projectId?: string) =>
    api.post<unknown, ApiResponse<any>>(
      '/knowledge/search',
      null,
      { params: { query, project_id: projectId } }
    ),
};

// ========== 全局变量/工作空间变量 ==========
export const globalVariableApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    scope?: string;
    project_id?: string;
    name?: string;
  }) => api.get<unknown, PageResponse<GlobalVariable>>('/variables', { params }),
  get: (id: string) =>
    api.get<unknown, ApiResponse<GlobalVariable>>(`/variables/${id}`),
  create: (data: GlobalVariableCreate) =>
    api.post<unknown, ApiResponse<GlobalVariable>>('/variables', data),
  update: (id: string, data: Partial<GlobalVariableCreate>) =>
    api.put<unknown, ApiResponse<GlobalVariable>>(`/variables/${id}`, data),
  delete: (id: string) =>
    api.delete<unknown, ApiResponse<GlobalVariable>>(`/variables/${id}`),
};

// ========== 认证快捷配置工具函数 ==========
// 认证类型
export type AuthType = 'none' | 'bearer' | 'oauth2' | 'api_key' | 'basic';

// 认证配置（纯前端组装，发送请求时合并到 headers/params）
export interface AuthConfig {
  type: AuthType;
  // Bearer / OAuth2
  token?: string;
  // API Key
  apiKeyName?: string;
  apiKeyValue?: string;
  apiKeyIn?: 'header' | 'query';
  // Basic Auth
  username?: string;
  password?: string;
}

/**
 * 将认证配置应用到请求 headers / params。
 * 返回合并后的 headers 和 params（不修改原始对象）。
 */
export function applyAuth(
  auth: AuthConfig | null | undefined,
  headers: Record<string, string>,
  params: Record<string, any>
): { headers: Record<string, string>; params: Record<string, any> } {
  if (!auth || auth.type === 'none') {
    return { headers: { ...headers }, params: { ...params } };
  }
  const mergedHeaders: Record<string, string> = { ...headers };
  const mergedParams: Record<string, any> = { ...params };

  switch (auth.type) {
    case 'bearer':
      if (auth.token) {
        mergedHeaders['Authorization'] = `Bearer ${auth.token}`;
      }
      break;
    case 'oauth2':
      if (auth.token) {
        mergedHeaders['Authorization'] = `Bearer ${auth.token}`;
      }
      break;
    case 'api_key':
      if (auth.apiKeyName && auth.apiKeyValue) {
        if (auth.apiKeyIn === 'query') {
          mergedParams[auth.apiKeyName] = auth.apiKeyValue;
        } else {
          mergedHeaders[auth.apiKeyName] = auth.apiKeyValue;
        }
      }
      break;
    case 'basic':
      if (auth.username !== undefined && auth.password !== undefined) {
        const credential = btoa(`${auth.username}:${auth.password}`);
        mergedHeaders['Authorization'] = `Basic ${credential}`;
      }
      break;
  }
  return { headers: mergedHeaders, params: mergedParams };
}

// ========== 任务中心（Jobs） ==========
export const jobsApi = {
  list: (params?: JobListParams) =>
    apiClient.get<unknown, PageResponse<Job>>('/jobs', { params }),
  get: (id: string) => apiClient.get<unknown, ApiResponse<Job>>(`/jobs/${id}`),
  create: (data: JobCreateInput) =>
    apiClient.post<unknown, ApiResponse<Job>>('/jobs', data),
  cancel: (id: string) =>
    apiClient.post<unknown, ApiResponse<Job>>(`/jobs/${id}/cancel`),
  retry: (id: string) =>
    apiClient.post<unknown, ApiResponse<Job>>(`/jobs/${id}/retry`),
  getEvents: (id: string, afterSequence?: number) =>
    apiClient.get<unknown, ApiResponse<JobEvent[]>>(`/jobs/${id}/events`, {
      params: { after_sequence: afterSequence || 0 },
    }),
  getArtifacts: (id: string) =>
    apiClient.get<unknown, ApiResponse<JobArtifact[]>>(`/jobs/${id}/artifacts`),
  getStreamUrl: (id: string, token: string) => {
    const configuredBase = apiClient.defaults.baseURL || '/api/v1';
    const baseUrl = new URL(configuredBase, window.location.origin);
    baseUrl.protocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    baseUrl.pathname = `${baseUrl.pathname.replace(/\/$/, '')}/jobs/${encodeURIComponent(id)}/stream`;
    baseUrl.search = new URLSearchParams({ token }).toString();
    return baseUrl.toString();
  },
};

// ========== Phase 5: 审计日志 / AI 运营 / 质量门禁 / 缺陷集成 ==========
export const auditLogApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    action?: string;
    resource_type?: string;
    actor_name?: string;
    start_time?: string;
    end_time?: string;
  }) => apiClient.get<unknown, PageResponse<any>>('/audit-logs', { params }),
};

export const aiOpsApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    model?: string;
    provider?: string;
    start_time?: string;
    end_time?: string;
  }) =>
    apiClient.get<unknown, PageResponse<any>>('/ai-ops/invocations', { params }),
  getStats: (days?: number) =>
    apiClient.get<unknown, ApiResponse<any>>('/ai-ops/stats', {
      params: days ? { days } : undefined,
    }),
  submitFeedback: (id: string, data: any) =>
    apiClient.post<unknown, ApiResponse<any>>(
      `/ai-ops/invocations/${id}/feedback`,
      data
    ),
};

export const qualityGateApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    project_id?: string;
    is_active?: boolean;
  }) => apiClient.get<unknown, PageResponse<any>>('/quality-gates', { params }),
  create: (data: any) =>
    apiClient.post<unknown, ApiResponse<any>>('/quality-gates', data),
  update: (id: string, data: any) =>
    apiClient.put<unknown, ApiResponse<any>>(`/quality-gates/${id}`, data),
  delete: (id: string) =>
    apiClient.delete<unknown, ApiResponse<any>>(`/quality-gates/${id}`),
};

export const defectApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    severity?: string;
    project_id?: string;
    external_system?: string;
  }) => apiClient.get<unknown, PageResponse<any>>('/defects', { params }),
  create: (data: any) =>
    apiClient.post<unknown, ApiResponse<any>>('/defects', data),
  get: (id: string) =>
    apiClient.get<unknown, ApiResponse<any>>(`/defects/${id}`),
  update: (id: string, data: any) =>
    apiClient.put<unknown, ApiResponse<any>>(`/defects/${id}`, data),
  sync: (id: string) =>
    apiClient.post<unknown, ApiResponse<any>>(`/defects/${id}/sync`),
};
