import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiResponse, Job, PageResponse, TestCase } from '../types';

vi.mock('../services/api', () => ({
  environmentApi: { list: vi.fn() },
  testCaseApi: { list: vi.fn() },
  testPlanApi: { list: vi.fn() },
  jobsApi: { list: vi.fn() },
  reportApi: { listRuns: vi.fn() },
}));

import DashboardPage from '../pages/DashboardPage';
import {
  environmentApi,
  jobsApi,
  reportApi,
  testCaseApi,
  testPlanApi,
} from '../services/api';

const mockedApis = {
  environments: vi.mocked(environmentApi.list),
  cases: vi.mocked(testCaseApi.list),
  plans: vi.mocked(testPlanApi.list),
  jobs: vi.mocked(jobsApi.list),
  reports: vi.mocked(reportApi.listRuns),
};

function pageResponse<T>(data: T[], total = data.length): PageResponse<T> {
  return {
    code: 0,
    message: 'ok',
    data,
    total,
    page: 1,
    page_size: Math.max(data.length, 1),
  };
}

function dataResponse<T>(data: T): ApiResponse<T> {
  return { code: 0, message: 'ok', data };
}

const recentCase: TestCase = {
  id: 'case-1',
  title: '查询用户资料',
  markers: ['smoke'],
  method: 'GET',
  url: '/api/users/me',
  headers: {},
  params: {},
  extract_rules: [],
  retry_count: 0,
  retry_interval: 0,
  is_active: true,
  sort_order: 0,
  created_at: '2026-07-16T08:00:00Z',
  updated_at: '2026-07-17T08:00:00Z',
};

const recentJob: Job = {
  id: 'job-1',
  job_type: 'api_case',
  status: 'succeeded',
  priority: 0,
  timeout_seconds: 300,
  result_summary: '用例执行通过',
  created_at: '2026-07-17T08:00:00Z',
  finished_at: '2026-07-17T08:00:02Z',
};

function mockSuccessfulLoad() {
  mockedApis.environments.mockResolvedValue(pageResponse([], 2));
  mockedApis.cases.mockResolvedValue(pageResponse([recentCase], 12));
  mockedApis.plans.mockResolvedValue(pageResponse([], 3));
  mockedApis.jobs.mockResolvedValue(pageResponse([recentJob], 1));
  mockedApis.reports.mockResolvedValue(
    dataResponse([
      { run_id: 'run-1', total: 8, passed: 7 },
      { run_id: 'run-2', total: 2, passed: 2 },
    ])
  );
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/quick-test" element={<div>接口调试目标页</div>} />
        <Route path="/api-list" element={<div>接口列表目标页</div>} />
        <Route path="/jobs" element={<div>任务中心目标页</div>} />
        <Route path="/reports" element={<div>报告目标页</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
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
  Object.defineProperty(globalThis, 'ResizeObserver', {
    configurable: true,
    value: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  });
});

describe('DashboardPage', () => {
  it('loads all workspace sources and renders compact execution data', async () => {
    mockSuccessfulLoad();
    renderDashboard();

    expect(await screen.findByText('个人测试工作台')).toBeInTheDocument();
    expect(mockedApis.environments).toHaveBeenCalledWith({ page: 1, page_size: 1 });
    expect(mockedApis.cases).toHaveBeenCalledWith({ page: 1, page_size: 6 });
    expect(mockedApis.plans).toHaveBeenCalledWith({ page: 1, page_size: 1 });
    expect(mockedApis.jobs).toHaveBeenCalledWith({ page: 1, page_size: 6 });
    expect(mockedApis.reports).toHaveBeenCalledWith(10);

    const stats = screen.getByTestId('stats-cards');
    expect(within(stats).getByText('12')).toBeInTheDocument();
    expect(within(stats).getByText('2')).toBeInTheDocument();
    expect(within(stats).getByText('3')).toBeInTheDocument();
    expect(stats).toHaveTextContent('90.0%');

    expect(within(screen.getByTestId('recent-jobs')).getByText('API 用例')).toBeInTheDocument();
    expect(within(screen.getByTestId('recent-jobs')).getByText('成功')).toBeInTheDocument();
    expect(within(screen.getByTestId('recent-cases')).getByText('查询用户资料')).toBeInTheDocument();
  });

  it('shows failed sources and retries instead of silently hiding errors', async () => {
    mockSuccessfulLoad();
    mockedApis.environments
      .mockRejectedValueOnce(new Error('后端连接失败'))
      .mockResolvedValueOnce(pageResponse([], 4));

    renderDashboard();

    const alert = await screen.findByTestId('dashboard-error');
    expect(alert).toHaveTextContent('环境数据：后端连接失败');

    fireEvent.click(within(alert).getByRole('button', { name: /重\s*试/ }));

    await waitFor(() => {
      expect(mockedApis.environments).toHaveBeenCalledTimes(2);
      expect(screen.queryByTestId('dashboard-error')).not.toBeInTheDocument();
    });
    expect(within(screen.getByTestId('stats-cards')).getByText('4')).toBeInTheDocument();
  });

  it('navigates from the explicit workspace shortcuts', async () => {
    mockSuccessfulLoad();
    renderDashboard();

    const shortcuts = await screen.findByTestId('quick-actions');
    fireEvent.click(within(shortcuts).getByRole('button', { name: /任务中心/ }));

    expect(await screen.findByText('任务中心目标页')).toBeInTheDocument();
  });
});
