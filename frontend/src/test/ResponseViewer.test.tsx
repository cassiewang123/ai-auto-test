import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import ResponseViewer from '../components/quick-test/ResponseViewer';
import type { ExecutionResultData } from '../services/api';

// 后端 headers 是 Record<string, string>；多值 set-cookie 的解析在 httpResponse 单测里覆盖
const response: NonNullable<ExecutionResultData['response']> = {
  status_code: 200,
  headers: {
    'content-type': 'application/json',
    'set-cookie': 'sid=abc123; Path=/; Domain=.example.com; Expires=Wed, 21 Oct 2037 07:28:00 GMT',
  },
  body: { code: 0, data: { name: 'Ada' } },
  elapsed: 0.1234,
  text: '{"code":0,"data":{"name":"Ada"}}',
};

describe('ResponseViewer', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  async function render() {
    await act(async () => {
      root.render(<ResponseViewer response={response} />);
    });
  }

  it('展示状态码、耗时与响应体积', async () => {
    await render();
    const status = container.querySelector('[data-testid="response-status"]');
    expect(status?.textContent).toBe('200');
    expect(container.textContent).toContain('0.1234s');
    // Body 文本约 40 字节，格式化后应落在 B/KB 档
    expect(container.textContent).toMatch(/\d+(\.\d+)?\s?(B|KB)/);
  });

  it('Body 默认美化输出并带复制按钮', async () => {
    await render();
    const body = container.querySelector('[data-testid="response-body"]');
    expect(body?.textContent).toContain('"name": "Ada"');
    expect(container.querySelector('[data-testid="copy-response-body"]')).toBeTruthy();
  });

  it('pretty/raw 切换可改变 Body 渲染', async () => {
    await render();
    const rawOption = Array.from(container.querySelectorAll('.ant-segmented-item-label')).find(
      (element) => element.textContent?.trim() === 'raw'
    );
    expect(rawOption).toBeTruthy();
    await act(async () => {
      rawOption?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    const body = container.querySelector('[data-testid="response-body"]');
    expect(body?.textContent).toBe(response.text);
  });

  it('Cookies Tab 从 set-cookie 解析出条目', async () => {
    await render();
    const cookiesTab = Array.from(container.querySelectorAll('.ant-tabs-tab-btn')).find(
      (element) => element.textContent?.includes('Cookies')
    );
    expect(cookiesTab?.textContent).toContain('(1)');
    await act(async () => {
      cookiesTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(container.textContent).toContain('sid');
    expect(container.textContent).toContain('.example.com');
  });
});
