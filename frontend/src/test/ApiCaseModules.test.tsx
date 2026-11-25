/**
 * 接口用例生成/用例管理页的模块（分组）交互测试。
 *
 * 关注点：生成页能按模块选择接口并逐接口生成、结果带上来源模块；
 * 用例管理页能按模块分组展示、点击用例进入编辑并保存。
 *
 * 页面统一用 StrictMode 包裹渲染：main.tsx 就是这么挂载的，StrictMode 会
 * 重复执行 effect，曾导致编辑弹窗的字段被清空（详见编辑用例的两个用例）。
 */
import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { messageSuccess, messageError, messageWarning } = vi.hoisted(() => ({
  messageSuccess: vi.fn(),
  messageError: vi.fn(),
  messageWarning: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      success: messageSuccess,
      error: messageError,
      warning: messageWarning,
      info: vi.fn(),
    },
  };
});

const testCaseList = vi.fn();
const generateTestCases = vi.fn();
const bulkImport = vi.fn();

vi.mock('../services/api', () => ({
  testCaseApi: {
    list: (...args: unknown[]) => testCaseList(...args),
  },
  aiApi: {
    generateTestCases: (...args: unknown[]) => generateTestCases(...args),
  },
  projectApi: {
    listAll: vi.fn().mockResolvedValue({ data: [] }),
  },
  apiCaseRecordApi: {
    list: vi.fn(),
    stats: vi.fn(),
    groups: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    batchMove: vi.fn(),
    batchDelete: vi.fn(),
    bulkImport: (...args: unknown[]) => bulkImport(...args),
    exportUrl: vi.fn(() => '/api/v1/api-cases/export'),
  },
}));

import { apiCaseRecordApi } from '../services/api';
import ApiCaseGenerationPage from '../pages/ApiCaseGenerationPage';
import ApiCaseManagementPage from '../pages/ApiCaseManagementPage';

const interfaceFixtures = [
  {
    id: 'if-1',
    title: '新增反馈',
    method: 'POST',
    url: '/api/feedback',
    group_path: '磐石关务/回执',
  },
  {
    id: 'if-2',
    title: '查询回执',
    method: 'GET',
    url: '/api/receipt',
    group_path: '磐石关务/回执',
  },
  {
    id: 'if-3',
    title: '报文发送',
    method: 'POST',
    url: '/api/message',
    group_path: '磐石关务/报文',
  },
];

const caseFixtures = [
  {
    id: 'case-1',
    title: '新增反馈-正常场景',
    method: 'POST',
    url: '/api/feedback',
    headers: {},
    params: {},
    body: { a: 1 },
    assertions: [{ type: 'status_code', expected: 200 }],
    case_type: 'normal',
    priority: 'P0',
    status: 'active',
    group_path: '磐石关务/回执',
    interface_name: '新增反馈',
    created_at: '2026-11-25T10:00:00',
  },
  {
    id: 'case-2',
    title: '报文发送-边界值',
    method: 'POST',
    url: '/api/message',
    headers: {},
    params: {},
    body: null,
    assertions: [],
    case_type: 'boundary',
    priority: 'P1',
    status: 'active',
    group_path: '磐石关务/报文',
    interface_name: '报文发送',
    created_at: '2026-11-25T10:00:00',
  },
];

function renderPage(node: React.ReactElement) {
  return render(
    <StrictMode>
      <MemoryRouter>{node}</MemoryRouter>
    </StrictMode>
  );
}

describe('接口用例生成页 - 按模块生成', () => {
  beforeEach(() => {
    messageSuccess.mockReset();
    messageError.mockReset();
    messageWarning.mockReset();
    testCaseList.mockReset();
    generateTestCases.mockReset();
    bulkImport.mockReset();
    testCaseList.mockResolvedValue({ data: interfaceFixtures, total: 3 });
  });

  it('切换到按模块后显示模块目录与接口数量', async () => {
    renderPage(<ApiCaseGenerationPage />);

    await waitFor(() => expect(testCaseList).toHaveBeenCalled());
    fireEvent.click(screen.getByText('按模块（分组）'));

    expect(await screen.findByText('模块目录（点击选择）')).toBeInTheDocument();
    expect(screen.getByText('请选择模块')).toBeInTheDocument();
  });

  it('选中模块后对该模块下所有接口逐个生成用例，并带上来源接口', async () => {
    generateTestCases.mockImplementation(async (payload: any) => ({
      data: {
        cases: [
          {
            title: `${payload.source_data.name}-正常`,
            case_type: 'normal',
            priority: 'P0',
            method: payload.source_data.method,
            url: payload.source_data.url,
            params: {},
            body: null,
            assertions: [{ type: 'status_code', expected: 200 }],
          },
        ],
      },
    }));

    renderPage(<ApiCaseGenerationPage />);
    await waitFor(() => expect(testCaseList).toHaveBeenCalled());
    fireEvent.click(screen.getByText('按模块（分组）'));

    // 模块树里点击「回执」（其下有 2 个接口）
    fireEvent.click(await screen.findByText('回执'));

    expect(await screen.findByText(/当前模块接口：2 个/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /按模块生成用例/ }));

    await waitFor(() => expect(generateTestCases).toHaveBeenCalledTimes(2));
    // 只应生成「回执」模块下的两个接口
    const names = generateTestCases.mock.calls.map(
      (call) => call[0].source_data.name
    );
    expect(names).toEqual(['新增反馈', '查询回执']);

    expect(await screen.findByText('新增反馈-正常')).toBeInTheDocument();
    expect(screen.getByText('查询回执-正常')).toBeInTheDocument();
  });

  it('按模块导入时把来源接口与模块透传给后端', async () => {
    generateTestCases.mockResolvedValue({
      data: {
        cases: [
          {
            title: '查询回执-异常',
            case_type: 'exception',
            priority: 'P1',
            method: 'GET',
            url: '/api/receipt',
            assertions: [],
          },
        ],
      },
    });
    bulkImport.mockResolvedValue({ data: { created_count: 2, case_ids: [] } });

    renderPage(<ApiCaseGenerationPage />);
    await waitFor(() => expect(testCaseList).toHaveBeenCalled());
    fireEvent.click(screen.getByText('按模块（分组）'));
    fireEvent.click(await screen.findByText('回执'));
    fireEvent.click(screen.getByRole('button', { name: /按模块生成用例/ }));

    await waitFor(() => expect(generateTestCases).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole('button', { name: /导入用例管理/ }));

    await waitFor(() => expect(bulkImport).toHaveBeenCalled());
    const payload = bulkImport.mock.calls[0][0];
    expect(payload.cases).toHaveLength(2);
    // 每条用例自带模块与接口名，后端按用例粒度落库
    expect(payload.cases[0]).toMatchObject({
      interface_name: '新增反馈',
      group_path: '磐石关务/回执',
    });
    expect(payload.cases[1]).toMatchObject({
      interface_name: '查询回执',
      group_path: '磐石关务/回执',
    });
    // 模块模式不再下发请求级接口名，避免覆盖用例级归属
    expect(payload.interface_name).toBeNull();
    expect(payload.group_path).toBeNull();
  });
});

describe('用例管理页 - 按模块显示与编辑', () => {
  beforeEach(() => {
    messageSuccess.mockReset();
    messageError.mockReset();
    (apiCaseRecordApi.list as unknown as ReturnType<typeof vi.fn>).mockReset();
    (apiCaseRecordApi.stats as unknown as ReturnType<typeof vi.fn>).mockReset();
    (apiCaseRecordApi.groups as unknown as ReturnType<typeof vi.fn>).mockReset();
    (apiCaseRecordApi.update as unknown as ReturnType<typeof vi.fn>).mockReset();

    (apiCaseRecordApi.list as any).mockResolvedValue({
      data: caseFixtures,
      total: 2,
    });
    (apiCaseRecordApi.stats as any).mockResolvedValue({
      data: { total: 2, group_count: 2, normal: 1, exception: 0, boundary: 1, p0: 1 },
    });
    (apiCaseRecordApi.groups as any).mockResolvedValue({
      data: [
        {
          path: '磐石关务/回执',
          name: '回执',
          parent_path: '磐石关务',
          direct_count: 1,
          total_count: 1,
        },
        {
          path: '磐石关务/报文',
          name: '报文',
          parent_path: '磐石关务',
          direct_count: 1,
          total_count: 1,
        },
      ],
    });
  });

  it('默认按模块分组显示，每个模块一张表', async () => {
    renderPage(<ApiCaseManagementPage />);

    expect(await screen.findByText('新增反馈-正常场景')).toBeInTheDocument();
    expect(screen.getByText('报文发送-边界值')).toBeInTheDocument();
    // 模块标题（分组卡片）沿路径展示
    expect(screen.getAllByText('磐石关务/回执').length).toBeGreaterThan(0);
    expect(screen.getByText('按模块分组')).toBeInTheDocument();
    expect(screen.getByText('模块数')).toBeInTheDocument();
  });

  it('点击用例标题进入编辑，保存后调用更新接口', async () => {
    (apiCaseRecordApi.update as any).mockResolvedValue({
      data: { ...caseFixtures[0], title: '改名后的用例' },
    });

    renderPage(<ApiCaseManagementPage />);
    fireEvent.click(await screen.findByText('新增反馈-正常场景'));

    // 编辑弹窗打开，标题输入框带出原值
    const dialog = await screen.findByRole('dialog');
    const titleInput = await within(dialog).findByDisplayValue('新增反馈-正常场景');
    expect(titleInput).toBeInTheDocument();

    fireEvent.change(titleInput, { target: { value: '改名后的用例' } });
    // antd 会在两个汉字的按钮文案中间插入空格（「保 存」），用正则匹配
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }));

    await waitFor(() => expect(apiCaseRecordApi.update).toHaveBeenCalled());
    const [id, payload] = (apiCaseRecordApi.update as any).mock.calls[0];
    expect(id).toBe('case-1');
    expect(payload.title).toBe('改名后的用例');
    // JSON 字段被解析成对象/数组而不是字符串
    expect(payload.headers).toEqual({});
    expect(payload.assertions).toEqual([{ type: 'status_code', expected: 200 }]);
    expect(payload.body).toEqual({ a: 1 });
  });

  it('编辑时 JSON 写错会拦截保存并提示', async () => {
    renderPage(<ApiCaseManagementPage />);
    fireEvent.click(await screen.findByText('新增反馈-正常场景'));

    const dialog = await screen.findByRole('dialog');
    const assertionsInput = await within(dialog).findByDisplayValue(/status_code/);
    fireEvent.change(assertionsInput, { target: { value: '{{broken' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }));

    await waitFor(() => expect(messageError).toHaveBeenCalled());
    expect(apiCaseRecordApi.update).not.toHaveBeenCalled();
  });

  it('编辑弹窗要带出用例详情（方法/URL/场景/优先级/模块/JSON 字段）', async () => {
    renderPage(<ApiCaseManagementPage />);
    fireEvent.click(await screen.findByText('新增反馈-正常场景'));

    const dialog = await screen.findByRole('dialog');
    // 标题
    expect(
      await within(dialog).findByDisplayValue('新增反馈-正常场景')
    ).toBeInTheDocument();
    // 接口地址
    expect(within(dialog).getByDisplayValue('/api/feedback')).toBeInTheDocument();
    // 关联接口
    expect(within(dialog).getByDisplayValue('新增反馈')).toBeInTheDocument();
    // 请求体 / 断言 以格式化 JSON 呈现
    expect(within(dialog).getByDisplayValue(/"a": 1/)).toBeInTheDocument();
    expect(
      within(dialog).getByDisplayValue(/status_code/)
    ).toBeInTheDocument();
    // 下拉类字段要显示中文/原值，而不是空白
    expect(within(dialog).getByText('POST')).toBeInTheDocument();
    expect(within(dialog).getByText('正常')).toBeInTheDocument();
    expect(within(dialog).getByText('P0')).toBeInTheDocument();
    expect(within(dialog).getByText('已确认')).toBeInTheDocument();
  });

  it('先关掉一条再打开另一条，第二次也要带出对应详情', async () => {
    renderPage(<ApiCaseManagementPage />);

    // 先打开第一条并取消
    fireEvent.click(await screen.findByText('新增反馈-正常场景'));
    let dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /取\s*消/ }));
    await waitFor(() =>
      expect(screen.queryByDisplayValue('新增反馈-正常场景')).not.toBeInTheDocument()
    );

    // 再打开另一条，必须是它自己的数据，不能是空的也不能是上一条的
    fireEvent.click(screen.getByText('报文发送-边界值'));
    dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByDisplayValue('报文发送-边界值')
    ).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue('/api/message')).toBeInTheDocument();
    expect(within(dialog).getByText('边界')).toBeInTheDocument();
    expect(within(dialog).getByText('P1')).toBeInTheDocument();
  });
});
