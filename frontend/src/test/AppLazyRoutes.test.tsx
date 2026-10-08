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

    expect(await screen.findByTestId('username-input')).toBeInTheDocument();
    expect(screen.getByTestId('login-submit')).toBeInTheDocument();
  });
});
