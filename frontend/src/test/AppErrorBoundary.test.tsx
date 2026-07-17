import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AppErrorBoundary from '../components/AppErrorBoundary';

function BrokenPage(): never {
  throw new Error('route render failed');
}

describe('AppErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('renders a recoverable fallback when a page throws', () => {
    render(
      <AppErrorBoundary>
        <BrokenPage />
      </AppErrorBoundary>
    );

    expect(screen.getByTestId('app-error-boundary')).toBeInTheDocument();
    expect(screen.getByText('页面加载失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
  });
});
