import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AppLayout from '../components/AppLayout';

const authState = vi.hoisted(() => ({
  user: {
    id: 'user-1',
    username: 'tester',
    email: 'tester@example.com',
    is_active: true,
    is_superuser: false,
    roles: [],
  },
  loading: false,
  logout: vi.fn(),
}));

const workspaceState = vi.hoisted(() => ({
  projects: [
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
  ],
  environments: [
    {
      id: 'environment-1',
      name: '测试环境',
      base_url: 'http://test.local',
      variables: {},
      is_active: true,
      created_at: '2026-07-20T00:00:00Z',
      updated_at: '2026-07-20T00:00:00Z',
    },
  ],
  selectedProjectId: 'project-1',
  selectedEnvironmentId: 'environment-1',
  setSelectedProjectId: vi.fn(),
  setSelectedEnvironmentId: vi.fn(),
  loading: false,
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

vi.mock('../contexts/WorkspaceContext', () => ({
  useWorkspace: () => workspaceState,
}));

function mockMatchMedia() {
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
}

function mockResizeObserver() {
  class TestResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  Object.defineProperty(globalThis, 'ResizeObserver', {
    configurable: true,
    value: TestResizeObserver,
  });
}

describe('AppLayout workspace header', () => {
  beforeEach(() => {
    mockMatchMedia();
    mockResizeObserver();
    workspaceState.setSelectedProjectId.mockReset();
    workspaceState.setSelectedEnvironmentId.mockReset();
  });

  it('shows project and environment selectors without the date header', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<div>dashboard content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('workspace-project-select')).toBeInTheDocument();
    expect(
      screen.getByTestId('workspace-environment-select')
    ).toBeInTheDocument();
    expect(screen.getByText('订单项目')).toBeInTheDocument();
    expect(screen.getByText('测试环境')).toBeInTheDocument();
    expect(screen.queryByText(/\d{4}-\d{2}-\d{2}/)).not.toBeInTheDocument();
  });

  it('updates the selected project through the header selector', async () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<div>dashboard content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    fireEvent.mouseDown(screen.getByTestId('workspace-project-select'));
    const options = await screen.findAllByText('会员项目');
    fireEvent.click(options[0]);

    expect(workspaceState.setSelectedProjectId).toHaveBeenCalledWith(
      'project-2'
    );
  });
});
