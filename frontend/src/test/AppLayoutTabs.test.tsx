import { act, useEffect, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u1',
      username: 'admin',
      email: 'admin@example.com',
      is_active: true,
      is_superuser: true,
      roles: [],
    },
    logout: vi.fn(),
    loading: false,
  }),
}));

vi.mock('../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    projects: [{ id: 'p1', name: '磐石关务' }],
    environments: [],
    selectedProjectId: 'p1',
    selectedEnvironmentId: null,
    setSelectedProjectId: vi.fn(),
    setSelectedEnvironmentId: vi.fn(),
    loading: false,
  }),
}));

vi.mock('../services/api', () => ({
  projectApi: { listAll: vi.fn().mockResolvedValue({ data: [] }) },
  environmentApi: { list: vi.fn().mockResolvedValue({ data: { items: [] } }) },
}));

import { PageTabsProvider } from '../contexts/PageTabsContext';
import AppLayout from '../components/AppLayout';
import { setKeepAliveRoutes, resetKeepAliveRoutes } from '../components/KeepAliveOutlet';

function StubPage({ name }: { name: string }) {
  return <div data-testid="page-body">{name}</div>;
}

const testRoutes = [
  {
    element: <AppLayout />,
    children: [
      { path: '/dashboard', element: <StubPage name="仪表盘页" /> },
      { path: '/api-list', element: <StubPage name="接口定义页" /> },
      { path: '/test-cases', element: <StubPage name="用例管理页" /> },
    ],
  },
];

describe('AppLayout 标签页集成', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    window.sessionStorage.clear();
    setKeepAliveRoutes(testRoutes);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.sessionStorage.clear();
    resetKeepAliveRoutes();
  });

  function renderLayout() {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/dashboard']}>
          <PageTabsProvider>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="/dashboard" element={<StubPage name="仪表盘页" />} />
                <Route path="/api-list" element={<StubPage name="接口定义页" />} />
                <Route path="/test-cases" element={<StubPage name="用例管理页" />} />
              </Route>
            </Routes>
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

  /** 保活容器会同时保留多个页面，只取当前显示的页面内容 */
  function activePageText(): string | undefined {
    const active = container.querySelector<HTMLElement>(
      '[data-keep-alive-page][data-active="true"]'
    );
    return active?.querySelector('[data-testid="page-body"]')?.textContent ?? undefined;
  }

  function menuItem(label: string): HTMLElement {
    const item = Array.from(
      container.querySelectorAll<HTMLElement>('[data-testid="sidebar-menu"] .ant-menu-item')
    ).find((el) => (el.textContent || '').includes(label));
    if (!item) throw new Error(`未找到菜单项：${label}`);
    return item;
  }

  function expandMenu(label: string) {
    const submenu = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-menu-submenu-title')
    ).find((el) => (el.textContent || '').includes(label));
    if (!submenu) throw new Error(`未找到子菜单：${label}`);
    const isOpen = submenu.closest('.ant-menu-submenu')?.classList.contains('ant-menu-submenu-open');
    if (isOpen) return;
    act(() => {
      submenu.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  }

  it('点击左侧菜单在右侧打开标签，并切换内容', () => {
    renderLayout();

    expect(activePageText()).toBe('仪表盘页');
    expect(tabLabels()).toEqual(['仪表盘']);

    expandMenu('API 测试');

    act(() => {
      menuItem('接口定义').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(tabLabels()).toEqual(['仪表盘', '接口定义']);
    expect(activePageText()).toBe('接口定义页');

    act(() => {
      menuItem('用例管理').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(tabLabels()).toEqual(['仪表盘', '接口定义', '用例管理']);
    expect(activePageText()).toBe('用例管理页');

    // 点击已有标签可以切回旧页面，内容区随之切换
    const firstTab = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).find((el) => (el.textContent || '').includes('接口定义'));
    act(() => {
      firstTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(activePageText()).toBe('接口定义页');
    expect(tabLabels()).toEqual(['仪表盘', '接口定义', '用例管理']);
  });

  it('切回标签时页面组件不重新挂载，内容仍保留', () => {
    let mountCount = 0;
    function StatefulPage() {
      const [value, setValue] = useState('');
      useEffect(() => {
        mountCount += 1;
      }, []);
      return (
        <input
          data-testid="state-input"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      );
    }
    setKeepAliveRoutes([
      {
        element: <AppLayout />,
        children: [
          { path: '/dashboard', element: <StubPage name="仪表盘页" /> },
          { path: '/api-list', element: <StatefulPage /> },
        ],
      },
    ]);
    renderLayout();

    expandMenu('API 测试');
    act(() => {
      menuItem('接口定义').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(mountCount).toBe(1);

    const input = container.querySelector<HTMLInputElement>('[data-testid="state-input"]')!;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value'
      )?.set;
      setter?.call(input, '未保存的内容');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(input.value).toBe('未保存的内容');

    // 切到仪表盘标签再切回来
    const dashboardTab = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).find((el) => (el.textContent || '').includes('仪表盘'));
    act(() => {
      dashboardTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expandMenu('API 测试');
    act(() => {
      menuItem('接口定义').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(mountCount).toBe(1);
    expect(
      container.querySelector<HTMLInputElement>('[data-testid="state-input"]')!.value
    ).toBe('未保存的内容');
  });

  it('标签栏出现在内容区内、页面内容之上', () => {
    renderLayout();
    const tabs = container.querySelector('[data-testid="page-tabs"]');
    const body = container.querySelector('[data-testid="page-body"]');
    expect(tabs).not.toBeNull();
    expect(body).not.toBeNull();
    // tabs 在 DOM 中先于页面内容，保证视觉上位于上方
    expect(
      tabs!.compareDocumentPosition(body!) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });
});
