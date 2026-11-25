import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

/** 可按用例注入的 mock 状态（vi.hoisted 保证在 mock 工厂中可引用） */
const mockState = vi.hoisted(() => ({
  environments: [] as any[],
  selectedEnvironmentId: null as string | null,
  selectedProjectId: null as string | null,
  globalVariables: [] as any[],
}));

/** 工作区上下文用轻量替身，避免测试依赖真实 Provider 的接口请求 */
vi.mock('../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    environments: mockState.environments,
    selectedProjectId: mockState.selectedProjectId,
    selectedEnvironmentId: mockState.selectedEnvironmentId,
    setSelectedEnvironmentId: () => {},
    setSelectedProjectId: () => {},
  }),
}));

/** 页面挂载即请求历史、项目、全局变量，这里全部返回可注入结果 */
vi.mock('../services/api', () => ({
  historyApi: {
    list: () => Promise.resolve({ data: [], total: 0, page: 1, page_size: 20 }),
    get: () => Promise.resolve({ data: null }),
  },
  projectApi: { listAll: () => Promise.resolve({ data: [] }) },
  globalVariableApi: {
    list: () =>
      Promise.resolve({
        data: mockState.globalVariables,
        total: mockState.globalVariables.length,
        page: 1,
        page_size: 200,
      }),
  },
  executionApi: {
    run: () => Promise.resolve({ data: null }),
    runMultipart: () => Promise.resolve({ data: null }),
  },
  testCaseApi: {
    get: () => Promise.resolve({ data: null }),
    create: () => Promise.resolve({ data: null }),
    update: () => Promise.resolve({ data: null }),
  },
  applyAuth: (_auth: unknown, headers: any, params: any) => ({
    headers: { ...headers },
    params: { ...params },
  }),
}));

import QuickTestPage from '../pages/QuickTestPage';

describe('QuickTestPage 布局改造冒烟', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    // 每个用例重置可注入的 mock 状态
    mockState.environments = [];
    mockState.selectedEnvironmentId = null;
    mockState.selectedProjectId = null;
    mockState.globalVariables = [];
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
      root.render(
        <MemoryRouter initialEntries={['/quick-test']}>
          <QuickTestPage />
        </MemoryRouter>
      );
    });
  }

  /** 点击主 Tab（Params/Headers/Body/Auth/Tests） */
  async function openCoreTab(label: string) {
    const tab = Array.from(container.querySelectorAll('.ant-tabs-tab-btn')).find(
      (element) => (element.textContent ?? '').startsWith(label)
    );
    expect(tab, `未找到 Tab：${label}`).toBeTruthy();
    await act(async () => {
      tab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  }

  async function click(selector: string) {
    const element = container.querySelector(selector);
    expect(element, `未找到元素：${selector}`).toBeTruthy();
    await act(async () => {
      element?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    return element;
  }

  it('渲染上下分屏骨架与历史侧栏', async () => {
    await render();
    expect(container.querySelector('[data-testid="quick-test-workspace"]')).toBeTruthy();
    expect(container.querySelector('.quick-test-history-pane')).toBeTruthy();
    expect(container.querySelector('.quick-test-main-pane')).toBeTruthy();
    expect(container.querySelector('[data-testid="quick-test-history-panel"]')).toBeTruthy();
  });

  it('保留发送入口，并新增 cURL 互操作入口', async () => {
    await render();
    expect(container.querySelector('[data-testid="send-btn"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="save-btn"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="copy-curl-btn"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="import-curl-btn"]')).toBeTruthy();
    // 未载入 case_id 时保存按钮仍是「保存到接口列表」
    expect(container.textContent).toContain('保存到接口列表');
    // 未执行时不应出现取消按钮
    expect(container.querySelector('[data-testid="cancel-btn"]')).toBeNull();
    // URL 输入保留原 testid（AutoComplete 包装后子 Input 仍在）
    expect(container.querySelector('[data-testid="url-input"]')).toBeTruthy();
    // 变量面板入口计数文案：只数可引用变量
    expect(
      container.querySelector('[data-testid="variables-btn"]')?.textContent
    ).toMatch(/^可引用变量/);
  });

  it('Body Tab 提供类型选择器', async () => {
    await render();
    const bodyTab = Array.from(container.querySelectorAll('.ant-tabs-tab-btn')).find(
      (element) => element.textContent?.trim() === 'Body'
    );
    expect(bodyTab).toBeTruthy();
    await act(async () => {
      bodyTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(container.querySelector('[data-testid="request-body-editor"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="body-type-segmented"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="request-body-input"]')).toBeTruthy();
  });

  it('高级设置默认收起，且包含文件上传入口', async () => {
    await render();
    expect(container.textContent).toContain('高级设置');
    expect(container.textContent).toContain('文件上传');

    // 展开高级设置 → 环境变量 Tab：文案不再宣称 base_url 可引用
    const header = Array.from(container.querySelectorAll('.ant-collapse-header')).find(
      (element) => element.textContent?.includes('高级设置')
    );
    expect(header).toBeTruthy();
    await act(async () => {
      header?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    const variableTab = Array.from(container.querySelectorAll('.ant-tabs-tab-btn')).find(
      (element) => element.textContent?.trim().includes('环境变量')
    );
    expect(variableTab).toBeTruthy();
    await act(async () => {
      variableTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const text = container.textContent ?? '';
    expect(text).toContain('环境变量会自动作为默认值');
    expect(text).toContain('仅用于拼接相对 URL，不作为可引用变量');
    expect(text).not.toContain('base_url 与环境变量会自动作为默认值');

    // TextArea placeholder 不再以 base_url 作为示例
    const envTextarea = Array.from(container.querySelectorAll('textarea')).find((element) =>
      element.getAttribute('placeholder')?.includes('token')
    );
    expect(envTextarea).toBeTruthy();
    const placeholder = envTextarea?.getAttribute('placeholder') ?? '';
    expect(placeholder).not.toContain('base_url');
    expect(() => JSON.parse(placeholder)).not.toThrow();
  });

  it('A8：点击断言模板追加一条断言行且字段正确', async () => {
    await render();
    await openCoreTab('Tests');
    expect(container.querySelector('input[placeholder="期望值"]')).toBeNull();
    await click('[data-testid="assertion-template-biz-code"]');
    const expected = container.querySelector('input[placeholder="期望值"]') as HTMLInputElement;
    const expression = container.querySelector('input[placeholder="表达式"]') as HTMLInputElement;
    expect(expected.value).toBe('0');
    expect(expression.value).toBe('$.code');
  });

  it('A8：模板按追加插入，不覆盖已编辑的行', async () => {
    await render();
    await openCoreTab('Tests');
    await click('[data-testid="assertion-template-biz-code"]');
    await click('[data-testid="assertion-template-status-200"]');
    const expecteds = container.querySelectorAll('input[placeholder="期望值"]');
    expect(expecteds.length).toBe(2);
    expect((expecteds[0] as HTMLInputElement).value).toBe('0');
    expect((expecteds[1] as HTMLInputElement).value).toBe('200');
  });

  it('A9：变量面板列出环境与全局变量并标注来源与优先级', async () => {
    mockState.environments = [
      {
        id: 'env-1',
        name: '测试环境',
        base_url: 'https://env.example.com',
        variables: { token: 'env-token-value', page_size: 20 },
        is_active: true,
      },
    ];
    mockState.selectedEnvironmentId = 'env-1';
    mockState.globalVariables = [
      {
        id: 'gv-1',
        name: 'base_url',
        value: 'https://global.example.com',
        var_type: 'string',
        scope: 'global',
      },
      {
        id: 'gv-2',
        name: 'service_flag',
        value: 'on',
        var_type: 'string',
        scope: 'global',
      },
    ];
    await render();

    // 环境信息条：值仍展示，但紧邻文案与汇总文案都明确「不可引用」
    const envContext = container.querySelector('[data-testid="quick-test-environment-context"]');
    expect(envContext?.querySelector('code')?.textContent).toBe('https://env.example.com');
    expect(envContext?.textContent).toContain('仅用于相对 URL 前缀，不作为可引用变量');
    expect(
      envContext?.querySelector('.quick-test-environment-summary')?.textContent
    ).toContain('仅用于相对 URL 前缀，不可引用');
    expect(envContext?.textContent).not.toContain('自动提供 base_url 和');

    const button = await click('[data-testid="variables-btn"]');
    // 计数文案只数可引用变量（不含 base_url）
    expect(button?.textContent).toMatch(/^可引用变量（\d+）/);

    const panel = document.querySelector('[data-testid="variables-panel"]');
    expect(panel).toBeTruthy();
    expect(panel?.textContent).toContain('优先级：本页覆盖 > 环境 > 全局');

    // 环境来源：base_url 与 token
    expect(
      panel?.querySelector('[data-testid="variable-source-environment-base_url"]')?.textContent
    ).toBe('环境');
    // base_url 仍展示且值正确，但明确标注不可 {{}} 引用
    expect(
      panel?.querySelector('[data-testid="variable-value-environment-base_url"]')?.textContent
    ).toBe('https://env.example.com');
    expect(
      panel?.querySelector('[data-testid="variable-note-environment-base_url"]')?.textContent
    ).toContain('仅用于相对 URL 前缀');
    expect(
      panel?.querySelector('[data-testid="variables-base-url-note"]')?.textContent
    ).toContain('仅用于拼接相对 URL');
    expect(
      panel?.querySelector('[data-testid="variable-source-environment-token"]')?.textContent
    ).toBe('环境');
    // 敏感变量名脱敏
    expect(
      panel?.querySelector('[data-testid="variable-value-environment-token"]')?.textContent
    ).toContain('••••');
    // 全局来源：service_flag
    expect(
      panel?.querySelector('[data-testid="variable-source-global-service_flag"]')?.textContent
    ).toBe('全局/工作区');
    // base_url 同名冲突：环境的生效，全局的被覆盖
    const baseUrls = panel?.querySelectorAll('[data-testid^="variable-row-"][data-testid$="-base_url"]');
    expect(baseUrls?.length).toBe(2);
    expect(baseUrls?.[1].textContent).toContain('被覆盖');
  });

  it('A9：URL 输入 {{ 时弹出变量候选并补全', async () => {
    mockState.environments = [
      {
        id: 'env-1',
        name: '测试环境',
        base_url: 'https://env.example.com',
        variables: { token: 'env-token-value' },
        is_active: true,
      },
    ];
    mockState.selectedEnvironmentId = 'env-1';
    await render();

    const input = container.querySelector('[data-testid="url-input"]') as HTMLInputElement;
    expect(input).toBeTruthy();

    // 模拟输入未闭合的 {{ 占位符
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value'
      )?.set;
      valueSetter?.call(input, 'https://a.test/{{to');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const optionTexts = Array.from(document.querySelectorAll('.ant-select-item-option')).map(
      (element) => element.textContent ?? ''
    );
    expect(optionTexts.join(',')).toContain('token');

    // 点击候选 → 补全为 {{token}}
    const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find(
      (element) => element.textContent?.trim() === 'token'
    );
    expect(option).toBeTruthy();
    await act(async () => {
      option?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      option?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(input.value).toBe('https://a.test/{{token}}');
  });

  it('A9：{{ 候选排除 base_url，其他变量仍可引用', async () => {
    mockState.environments = [
      {
        id: 'env-1',
        name: '测试环境',
        base_url: 'https://env.example.com',
        variables: { token: 'env-token-value' },
        is_active: true,
      },
    ];
    mockState.selectedEnvironmentId = 'env-1';
    mockState.globalVariables = [
      {
        id: 'gv-1',
        name: 'service_flag',
        value: 'on',
        var_type: 'string',
        scope: 'global',
      },
    ];
    await render();

    const input = container.querySelector('[data-testid="url-input"]') as HTMLInputElement;
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value'
      )?.set;
      valueSetter?.call(input, 'https://a.test/{{');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const optionTexts = Array.from(document.querySelectorAll('.ant-select-item-option')).map(
      (element) => element.textContent?.trim() ?? ''
    );
    expect(optionTexts).not.toContain('base_url');
    expect(optionTexts).toContain('token');
    expect(optionTexts).toContain('service_flag');

    // 变量面板仍能看到 base_url 及其说明，与候选集合解耦
    await click('[data-testid="variables-btn"]');
    const panel = document.querySelector('[data-testid="variables-panel"]');
    expect(
      panel?.querySelector('[data-testid="variable-value-environment-base_url"]')?.textContent
    ).toBe('https://env.example.com');
    expect(
      panel?.querySelector('[data-testid="variable-note-environment-base_url"]')?.textContent
    ).toContain('不可引用');
  });
});
