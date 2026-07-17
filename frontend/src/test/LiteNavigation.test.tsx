import { describe, expect, it } from 'vitest';
import {
  allNavigationItems,
  findNavigationItemByPath,
  flattenLeafKeys,
  getNavigationItems,
  getOpenKeys,
  resolveAppMode,
  type NavigationItem,
} from '../components/navigation';

const rootKeys = (items: NavigationItem[]) => items.map((item) => item.key);

const findByKey = (items: NavigationItem[], key: string) =>
  items.find((item) => item.key === key);

describe('lite navigation', () => {
  it('defaults to lite mode unless full is explicitly configured', () => {
    expect(resolveAppMode(undefined)).toBe('lite');
    expect(resolveAppMode('lite')).toBe('lite');
    expect(resolveAppMode('unsupported')).toBe('lite');
    expect(resolveAppMode('full')).toBe('full');
    expect(resolveAppMode('FULL')).toBe('full');
  });

  it('keeps only the single-machine core menu in lite mode', () => {
    const liteItems = getNavigationItems('lite');

    expect(rootKeys(liteItems)).toEqual([
      '/dashboard',
      '/jobs',
      'api-test',
      'ui-test',
      'perf-test',
      '/reports',
      '/coverage',
      '/scheduled-tasks',
      '/environments',
      '/variables',
      '/projects',
      '/history',
      '/ai',
    ]);
    expect(flattenLeafKeys(liteItems)).not.toContain('/quality-gates');
    expect(flattenLeafKeys(liteItems)).not.toContain('/defects');
    expect(flattenLeafKeys(liteItems)).not.toContain('/ai-ops');
    expect(rootKeys(liteItems)).not.toContain('knowledge');
    expect(rootKeys(liteItems)).not.toContain('system');
  });

  it('preserves every API, UI and performance child entry in lite mode', () => {
    const liteItems = getNavigationItems('lite');
    const fullItems = getNavigationItems('full');

    for (const groupKey of ['api-test', 'ui-test', 'perf-test']) {
      expect(findByKey(liteItems, groupKey)?.children?.map((item) => item.key))
        .toEqual(findByKey(fullItems, groupKey)?.children?.map((item) => item.key));
    }
  });

  it('keeps the complete existing menu in full mode', () => {
    const fullItems = getNavigationItems('full');

    expect(fullItems).toBe(allNavigationItems);
    expect(rootKeys(fullItems)).toContain('knowledge');
    expect(rootKeys(fullItems)).toContain('system');
    expect(flattenLeafKeys(fullItems)).toEqual([
      '/dashboard',
      '/jobs',
      '/api-list',
      '/api-docs',
      '/quick-test',
      '/test-cases',
      '/test-plans',
      '/test-data',
      '/import',
      '/mock-service',
      '/ui-test-cases',
      '/ui-test-suites',
      '/step-library',
      '/ui-elements',
      '/ui-test-records',
      '/ui-test-logs',
      '/perf-tests',
      '/perf-reports',
      '/perf-dashboard',
      '/reports',
      '/coverage',
      '/quality-gates',
      '/defects',
      '/scheduled-tasks',
      '/environments',
      '/variables',
      '/projects',
      '/history',
      '/ai',
      '/ai-ops',
      '/knowledge/defects',
      '/knowledge/rules',
      '/knowledge/interfaces',
      '/users',
      '/roles',
      '/api-tokens',
      '/ci-cd',
      '/notifications',
      '/audit-logs',
    ]);
  });

  it('resolves titles and parent groups from the complete route metadata', () => {
    expect(
      findNavigationItemByPath(allNavigationItems, '/quality-gates')?.label
    ).toBe('质量门禁');
    expect(
      findNavigationItemByPath(allNavigationItems, '/knowledge/interfaces/detail')
        ?.label
    ).toBe('接口知识库');
    expect(
      findNavigationItemByPath(allNavigationItems, '/users')?.label
    ).toBe('用户管理');
    expect(getOpenKeys(allNavigationItems, '/test-data')).toEqual(['api-test']);
    expect(getOpenKeys(allNavigationItems, '/knowledge/rules')).toEqual([
      'knowledge',
    ]);
    expect(findNavigationItemByPath(allNavigationItems, '/missing')).toBeUndefined();
  });

  it('retains stable menu test ids after filtering', () => {
    const liteItems = getNavigationItems('lite');

    expect(findByKey(liteItems, '/dashboard')?.['data-testid']).toBe(
      'menu-dashboard'
    );
    expect(findByKey(liteItems, 'api-test')?.['data-testid']).toBe(
      'menu-api-test'
    );
    expect(
      findByKey(liteItems, 'api-test')?.children?.[0]?.['data-testid']
    ).toBe('menu-api-list');
  });
});
