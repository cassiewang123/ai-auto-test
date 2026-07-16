import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiResponse, Job, JobArtifact, JobEvent, PageResponse } from '../types';

const { messageError, messageSuccess } = vi.hoisted(() => ({
  messageError: vi.fn(),
  messageSuccess: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      error: messageError,
      success: messageSuccess,
    },
  };
});

vi.mock('../services/api', () => ({
  jobsApi: {
    list: vi.fn(),
    get: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
    getEvents: vi.fn(),
    getArtifacts: vi.fn(),
    getStreamUrl: vi.fn((id: string) => `ws://localhost/api/v1/jobs/${id}/stream`),
  },
}));

import JobsPage from '../pages/JobsPage';
import { jobsApi } from '../services/api';

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close = vi.fn();

  emitOpen() {
    this.onopen?.(new Event('open'));
  }

  emitMessage(payload: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(payload) }));
  }
}

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

let root: Root | null = null;
let container: HTMLDivElement | null = null;

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    job_type: 'api_case',
    status: 'queued',
    priority: 0,
    timeout_seconds: 300,
    created_at: '2026-07-15T01:00:00Z',
    queued_at: '2026-07-15T01:00:00Z',
    ...overrides,
  };
}

function pageResponse(jobs: Job[]): PageResponse<Job> {
  return {
    code: 0,
    message: 'ok',
    data: jobs,
    total: jobs.length,
    page: 1,
    page_size: 20,
  };
}

function dataResponse<T>(data: T): ApiResponse<T> {
  return { code: 0, message: 'ok', data };
}

async function renderPage() {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<JobsPage />);
  });
}

async function waitFor(assertion: () => void, timeout = 4000) {
  const deadline = Date.now() + timeout;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      assertion();
      return;
    } catch (error) {
      lastError = error;
    }
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 20));
    });
  }
  throw lastError;
}

function getByTestId(testId: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  if (!element) throw new Error(`未找到 data-testid="${testId}"`);
  return element;
}

function getTab(label: string): HTMLElement {
  const tab = Array.from(document.querySelectorAll<HTMLElement>('[role="tab"]')).find((element) =>
    element.textContent?.includes(label)
  );
  if (!tab) throw new Error(`未找到页签 "${label}"`);
  return tab;
}

function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

function expectPageText(text: string) {
  expect(document.body.textContent).toContain(text);
}

const mockedJobsApi = {
  list: vi.mocked(jobsApi.list),
  get: vi.mocked(jobsApi.get),
  cancel: vi.mocked(jobsApi.cancel),
  retry: vi.mocked(jobsApi.retry),
  getEvents: vi.mocked(jobsApi.getEvents),
  getArtifacts: vi.mocked(jobsApi.getArtifacts),
  getStreamUrl: vi.mocked(jobsApi.getStreamUrl),
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  MockWebSocket.instances = [];

  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(window, 'WebSocket', {
    configurable: true,
    writable: true,
    value: MockWebSocket,
  });
  Object.defineProperty(globalThis, 'ResizeObserver', {
    configurable: true,
    writable: true,
    value: MockResizeObserver,
  });

  mockedJobsApi.getEvents.mockResolvedValue(dataResponse([]));
  mockedJobsApi.getArtifacts.mockResolvedValue(dataResponse([]));
});

afterEach(async () => {
  if (root) {
    await act(async () => {
      root?.unmount();
    });
  }
  root = null;
  container = null;
  document.body.innerHTML = '';
});

describe('JobsPage', () => {
  it('shows backend states and does not treat placeholder success as real execution', async () => {
    const placeholderJob = makeJob({
      id: 'placeholder-job',
      job_type: 'ui_case',
      status: 'succeeded',
      started_at: '2026-07-15T01:00:01Z',
      finished_at: '2026-07-15T01:00:02Z',
      result_summary: 'ui_case 占位执行完成（待异步 runner 接入）',
    });
    const failedJob = makeJob({
      id: 'failed-job',
      status: 'failed',
      started_at: '2026-07-15T01:00:01Z',
      finished_at: '2026-07-15T01:00:03Z',
      error_code: 'assertion_failed',
    });
    mockedJobsApi.list.mockResolvedValue(pageResponse([placeholderJob, failedJob]));

    await renderPage();
    await waitFor(() => expectPageText('UI 用例'));

    expectPageText('占位执行');
    expectPageText('真实执行');
    expect((getByTestId('job-cancel-placeholder-job') as HTMLButtonElement).disabled).toBe(true);
    expect((getByTestId('job-retry-failed-job') as HTMLButtonElement).disabled).toBe(false);
  });

  it('renders error details, event payloads, and artifact metadata', async () => {
    const failedJob = makeJob({
      id: 'detail-job',
      job_type: 'ui_case',
      status: 'failed',
      resource_id: 'ui-case-1',
      project_id: 'project-1',
      created_by: 'user-1',
      assigned_worker_id: 'ui-worker-1',
      dispatch_mode: 'celery',
      dispatch_queue: 'airetest.ui',
      started_at: '2026-07-15T01:00:01Z',
      finished_at: '2026-07-15T01:00:04Z',
      result_summary: 'UI 用例执行失败',
      error_code: 'browser_launch_failed',
      error_message: '浏览器启动失败',
    });
    const events: JobEvent[] = [
      {
        id: 11,
        job_id: failedJob.id,
        sequence: 1,
        event_type: 'job.started',
        payload: '{"worker_id":"ui-worker-1"}',
        created_at: '2026-07-15T01:00:01Z',
      },
      {
        id: 12,
        job_id: failedJob.id,
        sequence: 2,
        event_type: 'job.failed',
        payload: '{"message":"浏览器启动失败"}',
        created_at: '2026-07-15T01:00:04Z',
      },
    ];
    const artifacts: JobArtifact[] = [
      {
        id: 'artifact-1',
        job_id: failedJob.id,
        artifact_type: 'trace',
        filename: 'trace.zip',
        storage_key: 'jobs/detail-job/trace.zip',
        size_bytes: 4096,
        created_at: '2026-07-15T01:00:04Z',
      },
    ];

    mockedJobsApi.list.mockResolvedValue(pageResponse([failedJob]));
    mockedJobsApi.get.mockResolvedValue(dataResponse(failedJob));
    mockedJobsApi.getEvents.mockResolvedValue(dataResponse(events));
    mockedJobsApi.getArtifacts.mockResolvedValue(dataResponse(artifacts));

    await renderPage();
    await waitFor(() => getByTestId('job-detail-detail-job'));
    click(getByTestId('job-detail-detail-job'));

    await waitFor(() => expectPageText('browser_launch_failed'));
    expect(getByTestId('job-error').textContent).toContain('浏览器启动失败');
    expectPageText('ui-worker-1');

    click(getTab('实时日志'));
    await waitFor(() => expect(getByTestId('job-live-log').textContent).toContain('job.failed'));
    expect(getByTestId('job-live-log').textContent).toContain('浏览器启动失败');

    click(getTab('产物'));
    await waitFor(() => expectPageText('trace.zip'));
    expectPageText('jobs/detail-job/trace.zip');
    expectPageText('当前接口仅提供产物元数据，未返回可下载地址');
  });

  it('only enables valid cancel and retry actions and calls the matching API', async () => {
    const queuedJob = makeJob({ id: 'queued-job', status: 'queued' });
    const failedJob = makeJob({
      id: 'retry-job',
      status: 'failed',
      started_at: '2026-07-15T01:00:01Z',
      finished_at: '2026-07-15T01:00:02Z',
    });
    const cancelledJob = makeJob({
      ...queuedJob,
      status: 'cancelled',
      finished_at: '2026-07-15T01:00:02Z',
    });
    const retriedJob = makeJob({ id: 'new-job', status: 'queued' });

    mockedJobsApi.list.mockResolvedValue(pageResponse([queuedJob, failedJob]));
    mockedJobsApi.cancel.mockResolvedValue(dataResponse(cancelledJob));
    mockedJobsApi.retry.mockResolvedValue(dataResponse(retriedJob));

    await renderPage();
    await waitFor(() => getByTestId('job-cancel-queued-job'));

    click(getByTestId('job-cancel-queued-job'));
    await waitFor(() => expect(mockedJobsApi.cancel).toHaveBeenCalledWith('queued-job'));
    expect(messageSuccess).toHaveBeenCalledWith('任务取消请求已提交');

    click(getByTestId('job-retry-retry-job'));
    await waitFor(() => expect(mockedJobsApi.retry).toHaveBeenCalledWith('retry-job'));
    expect(messageSuccess).toHaveBeenCalledWith('新任务已入队：new-job');

    await waitFor(() =>
      expect((getByTestId('job-retry-queued-job') as HTMLButtonElement).disabled).toBe(true)
    );
    await waitFor(() =>
      expect((getByTestId('job-cancel-retry-job') as HTMLButtonElement).disabled).toBe(true)
    );
  });

  it('appends WebSocket events and refreshes the terminal job state', async () => {
    const runningJob = makeJob({
      id: 'live-job',
      job_type: 'ui_case',
      status: 'running',
      started_at: '2026-07-15T01:00:01Z',
      assigned_worker_id: 'ui-worker-live',
    });
    const succeededJob = makeJob({
      ...runningJob,
      status: 'succeeded',
      finished_at: '2026-07-15T01:00:05Z',
      result_summary: 'UI 用例真实执行通过',
    });
    const initialEvent: JobEvent = {
      id: 20,
      job_id: runningJob.id,
      sequence: 1,
      event_type: 'job.started',
      payload: '{"worker_id":"ui-worker-live"}',
      created_at: '2026-07-15T01:00:01Z',
    };

    localStorage.setItem('access_token', 'test-token');
    mockedJobsApi.list.mockResolvedValue(pageResponse([runningJob]));
    mockedJobsApi.get
      .mockResolvedValueOnce(dataResponse(runningJob))
      .mockResolvedValue(dataResponse(succeededJob));
    mockedJobsApi.getEvents
      .mockResolvedValueOnce(dataResponse([initialEvent]))
      .mockResolvedValue(dataResponse([]));

    await renderPage();
    await waitFor(() => getByTestId('job-detail-live-job'));
    click(getByTestId('job-detail-live-job'));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const socket = MockWebSocket.instances[0];
    act(() => socket.emitOpen());

    await waitFor(() => getTab('实时日志'));
    click(getTab('实时日志'));
    expect(getByTestId('job-live-log').textContent).toContain('实时连接');

    act(() =>
      socket.emitMessage({
        id: 21,
        event_type: 'job.log',
        sequence: 2,
        payload: '{"message":"浏览器已启动"}',
        created_at: '2026-07-15T01:00:02Z',
      })
    );
    await waitFor(() => expectPageText('浏览器已启动'));

    act(() =>
      socket.emitMessage({
        event_type: 'done',
        status: 'succeeded',
      })
    );

    await waitFor(() => expect(getByTestId('job-live-log').textContent).toContain('任务已结束'));
    await waitFor(() => expect(mockedJobsApi.get).toHaveBeenCalledTimes(2));
    expect(socket.close).toHaveBeenCalled();
  });
});
