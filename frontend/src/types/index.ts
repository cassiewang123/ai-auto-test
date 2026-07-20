// API 类型定义，与后端 Schema 对齐

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  detail?: string;
}

export interface PageResponse<T = any> extends ApiResponse<T[]> {
  total: number;
  page: number;
  page_size: number;
}

// 数据库连接配置（与后端 Environment.db_config 对齐）
export interface DbConfig {
  db_type?: 'mysql' | 'sqlite' | 'postgres';
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
  driver?: string;
}

// 环境
export interface Environment {
  id: string;
  name: string;
  description?: string;
  base_url: string;
  variables: Record<string, any>;
  db_config?: DbConfig | null;
  cookies?: Array<{ name: string; value: string; domain?: string; path?: string }>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EnvironmentCreate {
  name: string;
  base_url: string;
  description?: string;
  variables?: Record<string, any>;
  db_config?: DbConfig | null;
  cookies?: Array<{ name: string; value: string; domain?: string; path?: string }>;
}

// 项目
export interface Project {
  id: string;
  name: string;
  description?: string;
  base_url?: string;
  code?: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  base_url?: string;
  code?: string;
}

// 测试用例
export interface AssertionRule {
  id?: string;
  test_case_id?: string;
  assertion_type: string;
  expression?: string;
  operator: string;
  expected?: string;
  priority: string;
  order: number;
}

export interface TestCase {
  id: string;
  title: string;
  description?: string;
  group_path?: string | null;
  markers: string[];
  method: string;
  url: string;
  headers: Record<string, string>;
  params: Record<string, any>;
  body?: any;
  graphql_query?: string;
  files?: any[];
  extract_rules: any[];
  retry_count: number;
  retry_interval: number;
  pre_script?: string;
  post_script?: string;
  is_active: boolean;
  sort_order: number;
  environment_id?: string;
  project_id?: string;
  assertions?: AssertionRule[];
  created_at: string;
  updated_at: string;
}

export interface TestCaseCreate {
  title: string;
  method: string;
  url: string;
  description?: string;
  group_path?: string | null;
  markers?: string[];
  headers?: Record<string, string>;
  params?: Record<string, any>;
  body?: any;
  graphql_query?: string;
  extract_rules?: any[];
  assertions?: Omit<AssertionRule, 'id' | 'test_case_id'>[];
  environment_id?: string;
  project_id?: string;
  retry_count?: number;
  retry_interval?: number;
  pre_script?: string;
  post_script?: string;
}

export interface TestCaseUpdate {
  title?: string;
  method?: string;
  url?: string;
  description?: string | null;
  group_path?: string | null;
  markers?: string[];
  headers?: Record<string, string>;
  params?: Record<string, any>;
  body?: any | null;
  graphql_query?: string | null;
  files?: any[] | null;
  extract_rules?: any[];
  environment_id?: string | null;
  project_id?: string | null;
  is_active?: boolean;
  sort_order?: number;
  retry_count?: number;
  retry_interval?: number;
  pre_script?: string | null;
  post_script?: string | null;
}

// 全局变量/工作空间变量
export interface GlobalVariable {
  id: string;
  name: string;
  value: string;
  var_type: 'string' | 'number' | 'boolean' | 'json';
  description?: string;
  scope: 'global' | 'workspace';
  project_id?: string;
  created_at: string;
  updated_at: string;
}

export interface GlobalVariableCreate {
  name: string;
  value: string;
  var_type: 'string' | 'number' | 'boolean' | 'json';
  description?: string;
  scope: 'global' | 'workspace';
  project_id?: string;
}

// 测试计划
export interface TestPlanItem {
  id: string;
  plan_id: string;
  test_case_id: string;
  order: number;
  test_case?: TestCase;
}

export interface TestPlan {
  id: string;
  project_id?: string;
  created_by?: string;
  name: string;
  description?: string;
  environment_id?: string;
  execution_mode: string;
  marker_filter?: string;
  stress_config?: any;
  is_active: boolean;
  items: TestPlanItem[];
  created_at: string;
  updated_at: string;
}

export interface TestPlanCreate {
  project_id: string;
  name: string;
  description?: string;
  environment_id?: string;
  execution_mode?: string;
  marker_filter?: string;
  stress_config?: any;
}

// 测试结果
export interface TestResult {
  id: string;
  run_id: string;
  test_case_id: string;
  status: string;
  duration: number;
  request_snapshot?: any;
  response_snapshot?: any;
  assertion_results?: any[];
  error_message?: string;
  error_traceback?: string;
  ai_analysis?: any;
  executed_at: string;
}

export interface TestRunSummary {
  run_id: string;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  duration_sum: number;
}

export interface TrendPoint {
  date: string;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
}

// UI 测试用例
export interface UiTestCase {
  id: string;
  title: string;
  description?: string;
  url: string;
  browser_type: string;
  steps: UiTestStep[];
  project_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UiTestStep {
  action: string; // navigate/click/input/assert/wait/screenshot
  selector?: string;
  value?: string;
  description?: string;
}

// UI 元素对象
export interface UiElement {
  id: string;
  name: string;
  selector_type: string; // css/xpath/id/name
  selector_value: string;
  page_url?: string;
  description?: string;
  project_id?: string;
  created_at: string;
  updated_at: string;
}

// 压测自定义阶段（custom 模式）
export interface PerfStage {
  duration: number;
  users: number;
  spawn_rate: number;
}

// SLA 阈值配置（功能16）
export interface PerfSla {
  response_time_p95?: number; // ms
  error_rate?: number; // 0-1 分数
  rps_min?: number;
}

// 性能测试场景
export interface PerformanceTest {
  id: string;
  name: string;
  description?: string;
  case_ids: string[];
  config: {
    users: number;
    spawn_rate: number;
    duration: number;
    ramp_up?: number;
    mode?: 'steady' | 'ramp' | 'peak' | 'custom'; // 功能14 压测模式
    ramp_config?: {
      start_users: number;
      step: number;
      stage_duration: number;
      max_users: number;
    };
    peak_config?: {
      peak_users: number;
      hold_duration: number;
    };
    custom_config?: {
      stages: PerfStage[];
    };
    sla?: PerfSla; // 功能16 SLA 阈值
  };
  project_id?: string;
  status: string; // idle/running/completed/failed
  last_run_at?: string;
  created_at: string;
  updated_at: string;
}

// 性能测试结果
export interface PerformanceResult {
  id: string;
  test_id: string;
  run_id: string;
  total_requests: number;
  success_requests: number;
  fail_requests: number;
  avg_response_time: number;
  min_response_time: number;
  max_response_time: number;
  p50: number;
  p90: number;
  p95: number;
  p99: number;
  rps: number;
  error_rate: number;
  duration: number;
  detail: Record<string, any>;
  sla_status?: 'passed' | 'failed' | 'warning' | null; // 功能16
  sla_details?: Record<string, any>;
  mode?: string | null; // 功能14
  created_at: string;
}

// UI 测试执行记录
export interface UiTestRecord {
  id: string;
  case_id: string;
  case_title: string;
  project_id?: string;
  project_name?: string;
  url: string;
  browser_type: string;
  status: string; // passed/failed/error
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  duration: number;
  error?: string;
  step_results?: any[];
  triggered_by: string;
  executed_at: string;
}

// 任务中心
export type JobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'timed_out';

export type JobType = 'api_case' | 'ui_case' | 'ui_suite' | 'performance';

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  resource_id?: string | null;
  project_id?: string | null;
  priority: number;
  created_by?: string | null;
  assigned_worker_id?: string | null;
  timeout_seconds: number;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  result_summary?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  celery_task_id?: string | null;
  dispatch_mode?: string | null;
  dispatch_queue?: string | null;
}

export type JobEventPayload = string | Record<string, unknown> | null;

export interface JobEvent {
  id: number;
  job_id: string;
  sequence: number;
  event_type: string;
  payload?: JobEventPayload;
  created_at?: string | null;
}

export interface JobArtifact {
  id: string;
  job_id: string;
  artifact_type: string;
  filename?: string | null;
  storage_key?: string | null;
  size_bytes?: number | null;
  created_at?: string | null;
}

export interface JobListParams {
  page?: number;
  page_size?: number;
  status?: JobStatus;
  job_type?: JobType;
}

export interface JobCreateInput {
  job_type: JobType;
  resource_id?: string;
  config?: Record<string, unknown>;
  project_id?: string;
  idempotency_key?: string;
  timeout_seconds?: number;
  max_attempts?: number;
}

export interface JobStreamEvent {
  id: number;
  event_type: string;
  sequence: number;
  payload?: JobEventPayload;
  created_at?: string | null;
}

export interface JobStreamDoneMessage {
  event_type: 'done';
  status: JobStatus | 'not_found';
}

export type JobStreamMessage = JobStreamEvent | JobStreamDoneMessage;
