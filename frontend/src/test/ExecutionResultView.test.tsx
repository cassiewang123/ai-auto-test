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

  it('业务状态失败时展示中文类型并标为失败', () => {
    act(() => {
      root.render(
        <ExecutionResultView
          result={makeResult({
            status: 'failed',
            response: {
              status_code: 200,
              headers: { 'content-type': 'application/json' },
              body: { flag: 'f', errorCode: 100, errorInfo: 'id not found', data: null },
              elapsed: 0.6,
              text: '{}',
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
                assertion_type: 'business_status',
                expression: 'flag',
                operator: 'eq',
                expected: 'passed',
                actual: 'failed',
                passed: false,
                message: "业务标志 flag='f' 表示失败",
              },
            ],
          })}
        />
      );
    });

    const text = container.textContent || '';
    // 断言类型以中文展示，而不是原始的 business_status
    expect(text).toContain('业务状态');
    expect(text).not.toContain('business_status');
    expect(text).toContain("业务标志 flag='f' 表示失败");
  });

  /** 切到「实际请求」标签页（Tabs 内容懒渲染） */
  function openRequestTab() {
    const tab = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).find((el) => el.textContent?.includes('实际请求'));
    expect(tab).toBeTruthy();
    act(() => {
      tab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  }

  it('实际请求展示请求行、查询参数、请求头与请求体', () => {
    act(() => {
      root.render(
        <ExecutionResultView
          result={makeResult({
            status: 'passed',
            request: {
              method: 'POST',
              url: 'http://gateway.example.com/apiService/queryPage',
              headers: { 'Content-Type': 'application/json', epToken: '****' },
              params: { page: 1, size: 20 },
              body: { offset: 1, keyword: 'abc' },
            },
          })}
        />
      );
    });

    openRequestTab();
    const text = container.textContent || '';

    // 请求行
    expect(text).toContain('请求行');
    expect(text).toContain('http://gateway.example.com/apiService/queryPage');
    // 查询参数：既给出拼好的完整地址，也给出结构化参数
    expect(text).toContain('完整地址（含查询参数）');
    expect(text).toContain('page=1');
    expect(text).toContain('size=20');
    expect(text).toContain('查询参数 (2)');
    // 请求头
    expect(text).toContain('请求头 (2)');
    expect(text).toContain('Content-Type');
    // 请求体
    expect(text).toContain('请求体');
    expect(text).toContain('"keyword": "abc"');
  });

  it('没有参数/请求头/请求体时给出明确说明而不是留白', () => {
    act(() => {
      root.render(
        <ExecutionResultView
          result={makeResult({
            status: 'passed',
            request: {
              method: 'GET',
              url: 'http://gateway.example.com/ping',
              headers: {},
              params: {},
              body: null,
            },
          })}
        />
      );
    });

    openRequestTab();
    const text = container.textContent || '';
    expect(text).toContain('未携带查询参数');
    expect(text).toContain('未携带自定义请求头');
    expect(text).toContain('无请求体');
    // 没有查询参数时不展示「完整地址」小节
    expect(text).not.toContain('完整地址（含查询参数）');
  });
});
