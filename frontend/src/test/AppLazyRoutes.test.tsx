import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    token: null,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
  },
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

describe('App lazy routes', () => {
  beforeEach(() => {
    mockMatchMedia();
    mockResizeObserver();
  });

  it('loads the lazy LoginPage route on /login', async () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>
    );

    // 并发全量跑时 lazy chunk 解析受 worker 竞争影响（隔离 678-691ms 通过、
    // 并发曾三次超 1s 默认超时），这里把等待上限放宽到 5s，断言本身不变。
    expect(
      await screen.findByTestId('username-input', undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(screen.getByTestId('login-submit')).toBeInTheDocument();
  });
});
