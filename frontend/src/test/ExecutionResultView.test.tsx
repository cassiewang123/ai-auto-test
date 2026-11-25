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

    // 实际请求与响应体同屏，无需切换标签即可看到真实请求地址
    expect(text).toContain('实际请求');
    expect(text).toContain(
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

  it('实际请求与响应体同时可见，无需切换标签', () => {
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

    const text = container.textContent || '';

    // 两张卡片都在页面上，不需要点标签
    expect(text).toContain('实际请求');
    expect(text).toContain('响应内容');
    // 「实际请求」不再是标签页
    const tabLabels = Array.from(
      container.querySelectorAll<HTMLElement>('.ant-tabs-tab')
    ).map((el) => el.textContent || '');
    expect(tabLabels.some((label) => label.includes('实际请求'))).toBe(false);
    expect(tabLabels.some((label) => label.includes('响应体'))).toBe(true);

    // —— 请求侧 ——
    expect(text).toContain('请求行');
    expect(text).toContain('http://gateway.example.com/apiService/queryPage');
    expect(text).toContain('完整地址（含查询参数）');
    expect(text).toContain('page=1');
    expect(text).toContain('size=20');
    expect(text).toContain('查询参数 (2)');
    expect(text).toContain('请求头 (2)');
    expect(text).toContain('Content-Type');
    expect(text).toContain('"keyword": "abc"');

    // —— 响应侧同时可见 ——
    expect(text).toContain('"total": 236');
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

    const text = container.textContent || '';
    expect(text).toContain('未携带查询参数');
    expect(text).toContain('未携带自定义请求头');
    expect(text).toContain('无请求体');
    // 没有查询参数时不展示「完整地址」小节
    expect(text).not.toContain('完整地址（含查询参数）');
  });

  it('只有请求没有响应时仍展示请求信息', () => {
    act(() => {
      root.render(
        <ExecutionResultView
          result={makeResult({
            status: 'error',
            response: null,
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

    const text = container.textContent || '';
    expect(text).toContain('实际请求');
    expect(text).toContain('请求行');
    expect(text).toContain('本次执行没有收到响应');
  });
});
