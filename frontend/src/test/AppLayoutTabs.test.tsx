import { act } from 'react';
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

function StubPage({ name }: { name: string }) {
  return <div data-testid="page-body">{name}</div>;
}

describe('AppLayout 标签页集成', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    window.sessionStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.sessionStorage.clear();
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
    act(() => {
      submenu.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  }

  it('点击左侧菜单在右侧打开标签，并切换内容', () => {
    renderLayout();

    expect(container.querySelector('[data-testid="page-body"]')?.textContent).toBe('仪表盘页');
    expect(tabLabels()).toEqual(['仪表盘']);

    expandMenu('API 测试');

    act(() => {
      menuItem('接口定义').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(tabLabels()).toEqual(['仪表盘', '接口定义']);
    expect(container.querySelector('[data-testid="page-body"]')?.textContent).toBe('接口定义页');

    act(() => {
      menuItem('用例管理').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(tabLabels()).toEqual(['仪表盘', '接口定义', '用例管理']);
    expect(container.querySelector('[data-testid="page-body"]')?.textContent).toBe('用例管理页');

    // 点击已有标签可以切回旧页面，内容区随之切换
    const firstTab = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).find((el) => (el.textContent || '').includes('接口定义'));
    act(() => {
      firstTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(container.querySelector('[data-testid="page-body"]')?.textContent).toBe('接口定义页');
    expect(tabLabels()).toEqual(['仪表盘', '接口定义', '用例管理']);
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
