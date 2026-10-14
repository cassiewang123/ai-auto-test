import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { PageTabsProvider, usePageTabs } from '../contexts/PageTabsContext';
import PageTabs from '../components/PageTabs';

let currentPath = '/dashboard';
let navigateTo: (path: string) => void = () => {};

function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  currentPath = location.pathname;
  navigateTo = navigate;
  return null;
}

describe('PageTabs 多标签页', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    window.sessionStorage.clear();
    currentPath = '/dashboard';
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.sessionStorage.clear();
  });

  function renderAt(path: string) {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={[path]}>
          <PageTabsProvider>
            <LocationProbe />
            <PageTabs />
          </PageTabsProvider>
        </MemoryRouter>
      );
    });
  }

  function tabLabels(): string[] {
    return Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).map((el) => (el.textContent || '').trim());
  }

  it('当前路由自动成为一个标签，并显示中文名称', () => {
    renderAt('/dashboard');
    expect(tabLabels()).toEqual(['仪表盘']);
  });

  it('打开新页面时追加标签，重复打开同一个页面不产生重复标签', () => {
    renderAt('/dashboard');
    act(() => navigateTo('/api-list'));
    act(() => navigateTo('/test-cases'));
    act(() => navigateTo('/api-list'));

    expect(tabLabels()).toEqual(['仪表盘', '接口定义', '用例管理']);
    expect(currentPath).toBe('/api-list');
  });

  it('关闭当前标签后回到相邻标签', () => {
    renderAt('/dashboard');
    act(() => navigateTo('/api-list'));
    act(() => navigateTo('/test-cases'));

    const closeButtons = container.querySelectorAll<HTMLElement>(
      '.ant-tabs-tab-remove'
    );
    // 用例管理是当前标签（最后一个），关闭后回到左侧相邻的接口定义
    act(() => {
      closeButtons[closeButtons.length - 1].dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      );
    });

    expect(tabLabels()).toEqual(['仪表盘', '接口定义']);
    expect(currentPath).toBe('/api-list');
  });

  it('首页标签不可关闭，其余标签可关闭', () => {
    renderAt('/dashboard');
    act(() => navigateTo('/reports'));

    const tabs = container.querySelectorAll('.ant-tabs-tab');
    expect(tabs).toHaveLength(2);
    expect(tabs[0].querySelector('.ant-tabs-tab-remove')).toBeNull();
    expect(tabs[1].querySelector('.ant-tabs-tab-remove')).not.toBeNull();
  });

  it('刷新页面后能从 sessionStorage 恢复已打开的标签', () => {
    window.sessionStorage.setItem(
      'airetest.page-tabs',
      JSON.stringify([
        { path: '/dashboard', label: '仪表盘' },
        { path: '/api-list', label: '接口定义' },
      ])
    );
    renderAt('/api-list');

    expect(tabLabels()).toEqual(['仪表盘', '接口定义']);
  });

  it('提供标签操作：关闭其他、关闭全部', () => {
    let helpers: ReturnType<typeof usePageTabs> | null = null;
    function Capture() {
      helpers = usePageTabs();
      return null;
    }
    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/dashboard']}>
          <PageTabsProvider>
            <LocationProbe />
            <Capture />
            <PageTabs />
          </PageTabsProvider>
        </MemoryRouter>
      );
    });
    act(() => navigateTo('/api-list'));
    act(() => navigateTo('/reports'));
    expect(tabLabels()).toHaveLength(3);

    act(() => helpers?.closeOtherTabs('/api-list'));
    expect(tabLabels()).toEqual(['接口定义']);
    expect(currentPath).toBe('/api-list');

    act(() => helpers?.closeAllTabs());
    // 全部关闭后自动回到首页，避免出现空白内容区
    expect(tabLabels()).toEqual(['仪表盘']);
    expect(currentPath).toBe('/dashboard');
  });
});
