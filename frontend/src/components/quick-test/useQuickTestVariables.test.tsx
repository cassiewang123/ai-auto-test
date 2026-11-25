import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, renderHook, waitFor } from '@testing-library/react';

const mockState = vi.hoisted(() => ({
  globalVariables: [] as any[],
}));

vi.mock('../../services/api', () => ({
  globalVariableApi: {
    list: () =>
      Promise.resolve({
        data: mockState.globalVariables,
        total: mockState.globalVariables.length,
        page: 1,
        page_size: 200,
      }),
  },
}));

import { useQuickTestVariables } from './useQuickTestVariables';

const environment = {
  id: 'env-1',
  name: '测试环境',
  base_url: 'https://env.example.com',
  variables: { token: 'env-token', page_size: 20 },
};

afterEach(() => {
  cleanup();
  mockState.globalVariables = [];
});

describe('useQuickTestVariables：base_url 语义', () => {
  it('base_url 只展示不进入可引用变量名集合', async () => {
    const { result } = renderHook(() =>
      useQuickTestVariables({
        environment,
        pageVariablesText: '{}',
        projectId: null,
      })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    const baseUrlEntry = result.current.entries.find(
      (entry) => entry.source === 'environment' && entry.name === 'base_url'
    );
    expect(baseUrlEntry?.value).toBe('https://env.example.com');
    expect(baseUrlEntry?.referenceable).toBe(false);
    expect(baseUrlEntry?.note).toContain('仅用于相对 URL 前缀');

    // 关键：{{}} 输入提示不再给出 base_url
    expect(result.current.names).not.toContain('base_url');
  });

  it('环境变量 / 全局变量 / 本页覆盖仍然可引用', async () => {
    mockState.globalVariables = [
      {
        id: 'gv-1',
        name: 'service_flag',
        value: 'on',
        var_type: 'string',
        scope: 'global',
      },
      {
        id: 'gv-2',
        name: 'region',
        value: 'cn',
        var_type: 'string',
        scope: 'workspace',
        project_id: 'project-1',
      },
    ];
    const { result } = renderHook(() =>
      useQuickTestVariables({
        environment,
        pageVariablesText: '{"local_page": 5}',
        projectId: 'project-1',
      })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.names).toEqual(
      expect.arrayContaining(['token', 'page_size', 'service_flag', 'region', 'local_page'])
    );
    expect(result.current.names).not.toContain('base_url');
    // 本页覆盖优先级最高，且仍可引用
    const local = result.current.entries.find((entry) => entry.name === 'local_page');
    expect(local?.source).toBe('page');
    expect(local?.referenceable).toBe(true);
  });

  it('无选中环境时不会出现 base_url 条目', async () => {
    const { result } = renderHook(() =>
      useQuickTestVariables({
        environment: null,
        pageVariablesText: '{}',
        projectId: null,
      })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.entries.some((entry) => entry.name === 'base_url')).toBe(false);
    expect(result.current.names).toEqual([]);
  });
});
