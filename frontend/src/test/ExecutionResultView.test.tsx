import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import ExecutionResultView from '../components/ExecutionResultView';
import type { ExecutionResultData } from '../services/api';

function makeResult(overrides: Partial<ExecutionResultData> = {}): ExecutionResultData {
  return {
    test_case_id: 'case-1',
    status: 'failed',
    duration: 1.234,
    request: {
      method: 'POST',
      url: 'http://gateway.example.com/apiService/queryPage',
      headers: { epToken: '****' },
      params: {},
      body: { offset: 1 },
    },
    response: {
      status_code: 200,
      headers: { 'content-type': 'application/json' },
      body: { code: 200, data: { total: 236 } },
      elapsed: 1.2,
      text: '{"code":200,"data":{"total":236}}',
    },
    assertion_results: [
      {
        assertion_type: 'status_code',
        expression: null,
        operator: 'eq',
        expected: 200,
        actual: 200,
        passed: true,
        message: '',
      },
      {
        assertion_type: 'json_path',
        expression: '$.code',
        operator: 'eq',
        expected: '200',
        actual: 404,
        passed: false,
        message: '期望 200，实际 404',
      },
    ],
    extracted_variables: [],
    error_message: null,
    executed_at: '2026-10-14T03:13:07',
    ...overrides,
  };
}

describe('ExecutionResultView', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('展示状态、耗时、状态码与断言明细', () => {
    act(() => {
      root.render(<ExecutionResultView result={makeResult()} />);
    });

    const text = container.textContent || '';
    expect(text).toContain('失败');
    expect(text).toContain('1.234s');
    expect(text).toContain('HTTP 状态码');
    expect(text).toContain('200');
    expect(text).toContain('断言');
    expect(text).toContain('2');
    expect(text).toContain('PASS');
    expect(text).toContain('FAIL');
    expect(text).toContain('$.code');
    expect(text).toContain('期望 200，实际 404');
    // 响应体应渲染出 JSON 内容
    expect(text).toContain('"total": 236');

    // 切到「实际请求」标签页可看到真实请求地址（含变量渲染后的 URL）
    const requestTab = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).find((el) => el.textContent?.includes('实际请求'));
    expect(requestTab).toBeTruthy();
    act(() => {
      requestTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(container.textContent).toContain(
      'http://gateway.example.com/apiService/queryPage'
    );
  });

  it('没有断言时也能正常渲染', () => {
    act(() => {
      root.render(
        <ExecutionResultView
          result={makeResult({ assertion_results: [], status: 'passed' })}
        />
      );
    });
    const text = container.textContent || '';
    expect(text).toContain('通过');
    expect(text).toContain('断言');
    expect(text).not.toContain('PASS');
  });

  it('无响应时展示提示而不是空白', () => {
    act(() => {
      root.render(
        <ExecutionResultView
          result={makeResult({
            response: null,
            assertion_results: [],
            status: 'error',
            error_message: 'UnsupportedProtocol: {{contentProtocol}}',
          })}
        />
      );
    });
    const text = container.textContent || '';
    expect(text).toContain('本次执行没有收到响应');
    expect(text).toContain('UnsupportedProtocol');
  });
});
