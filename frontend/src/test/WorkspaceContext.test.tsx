import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PropsWithChildren } from 'react';
import { WorkspaceProvider, useWorkspace } from '../contexts/WorkspaceContext';

const apiMocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listEnvironments: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  user: { id: 'user-1' } as { id: string } | null,
  loading: false,
}));

vi.mock('../services/api', () => ({
  projectApi: {
    listAll: apiMocks.listProjects,
  },
  environmentApi: {
    list: apiMocks.listEnvironments,
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

const projects = [
  {
    id: 'project-1',
    name: '订单项目',
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
  },
  {
    id: 'project-2',
    name: '会员项目',
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
  },
];

const environments = [
  {
    id: 'environment-1',
    name: '测试环境',
    base_url: 'http://test.local',
    variables: {},
    is_active: true,
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
  },
  {
    id: 'environment-2',
    name: '停用环境',
    base_url: 'http://disabled.local',
    variables: {},
    is_active: false,
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
  },
];

function wrapper({ children }: PropsWithChildren) {
  return <WorkspaceProvider>{children}</WorkspaceProvider>;
}

describe('WorkspaceContext', () => {
  beforeEach(() => {
    localStorage.clear();
    authState.user = { id: 'user-1' };
    authState.loading = false;
    apiMocks.listProjects.mockReset();
    apiMocks.listEnvironments.mockReset();
    apiMocks.listProjects.mockResolvedValue({ data: projects });
    apiMocks.listEnvironments.mockResolvedValue({
      data: environments,
    });
  });

  it('loads workspace data and restores persisted selections', async () => {
    localStorage.setItem('airetest.selectedProjectId', 'project-2');
    localStorage.setItem('airetest.selectedEnvironmentId', 'environment-1');

    const { result } = renderHook(() => useWorkspace(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(apiMocks.listProjects).toHaveBeenCalledTimes(1);
    expect(apiMocks.listEnvironments).toHaveBeenCalledWith({
      page: 1,
      page_size: 100,
    });
    expect(result.current.projects).toEqual(projects);
    expect(result.current.environments).toEqual(environments);
    expect(result.current.selectedProjectId).toBe('project-2');
    expect(result.current.selectedEnvironmentId).toBe('environment-1');
  });

  it('falls back to available project and active environment when storage is stale', async () => {
    localStorage.setItem('airetest.selectedProjectId', 'missing-project');
    localStorage.setItem('airetest.selectedEnvironmentId', 'missing-environment');

    const { result } = renderHook(() => useWorkspace(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.selectedProjectId).toBe('project-1');
    expect(result.current.selectedEnvironmentId).toBe('environment-1');
    expect(localStorage.getItem('airetest.selectedProjectId')).toBe('project-1');
    expect(localStorage.getItem('airetest.selectedEnvironmentId')).toBe(
      'environment-1'
    );
  });

  it('persists changes and supports clearing a selection', async () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setSelectedProjectId('project-2');
      result.current.setSelectedEnvironmentId(null);
    });

    expect(result.current.selectedProjectId).toBe('project-2');
    expect(localStorage.getItem('airetest.selectedProjectId')).toBe('project-2');
    expect(result.current.selectedEnvironmentId).toBeNull();
    expect(localStorage.getItem('airetest.selectedEnvironmentId')).toBeNull();
  });

  it('does not request workspace data before authentication completes', async () => {
    authState.user = null;

    const { result } = renderHook(() => useWorkspace(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(apiMocks.listProjects).not.toHaveBeenCalled();
    expect(apiMocks.listEnvironments).not.toHaveBeenCalled();
    expect(result.current.projects).toEqual([]);
    expect(result.current.environments).toEqual([]);
  });
});
