import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const listMock = vi.fn();
const statsMock = vi.fn();

vi.mock('../services/api', () => ({
  requirementApi: {
    list: (...args: unknown[]) => listMock(...args),
    stats: (...args: unknown[]) => statsMock(...args),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    listDocuments: vi.fn().mockResolvedValue({ data: [] }),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    analyze: vi.fn(),
    listAnalyses: vi.fn().mockResolvedValue({ data: [] }),
    getAnalysis: vi.fn(),
    continueAnalysis: vi.fn(),
    exportAnalysisUrl: vi.fn(),
  },
  knowledgeBaseApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    listDocuments: vi.fn().mockResolvedValue({ data: [], total: 0 }),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    reindexDocument: vi.fn(),
    listChunks: vi.fn().mockResolvedValue({ data: [], total: 0 }),
    rebuildIndex: vi.fn(),
    retrieve: vi.fn(),
    previewChunks: vi.fn(),
  },
  testDesignApi: {
    listSessions: vi.fn().mockResolvedValue({ data: [], total: 0 }),
    createSession: vi.fn(),
    getSession: vi.fn(),
    removeSession: vi.fn(),
    sendMessage: vi.fn(),
    generatePoints: vi.fn(),
    updatePoints: vi.fn(),
    generateCases: vi.fn(),
    review: vi.fn(),
    importCases: vi.fn(),
  },
  projectApi: {
    listAll: vi.fn().mockResolvedValue({ data: [] }),
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

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('需求管理页面', () => {
  beforeEach(() => {
    mockMatchMedia();
    Object.defineProperty(globalThis, 'ResizeObserver', {
      configurable: true,
      value: TestResizeObserver,
    });
    listMock.mockReset();
    statsMock.mockReset();
    statsMock.mockResolvedValue({ data: { total: 0 } });
  });

  it('渲染需求列表并提供需求分析入口', async () => {
    listMock.mockResolvedValue({
      data: [
        {
          id: 'req-1',
          title: '登录、项目、需求管理需求',
          priority: 'P0',
          status: 'draft',
          coverage: 3,
        },
      ],
      total: 1,
    });

    const { default: RequirementsPage } = await import('../pages/RequirementsPage');
    render(
      <MemoryRouter>
        <RequirementsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('登录、项目、需求管理需求')).toBeInTheDocument();
    expect(screen.getByText('需求分析')).toBeInTheDocument();
    expect(screen.getByText('新建需求')).toBeInTheDocument();
  });

  it('列表为空时展示表格而不是崩溃', async () => {
    listMock.mockResolvedValue({ data: [], total: 0 });

    const { default: RequirementsPage } = await import('../pages/RequirementsPage');
    render(
      <MemoryRouter>
        <RequirementsPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(screen.getByText('需求管理')).toBeInTheDocument();
  });
});

describe('知识库页面', () => {
  beforeEach(() => {
    mockMatchMedia();
    Object.defineProperty(globalThis, 'ResizeObserver', {
      configurable: true,
      value: TestResizeObserver,
    });
  });

  it('没有知识库时给出创建引导', async () => {
    const { default: KnowledgeBasesPage } = await import(
      '../pages/KnowledgeBasesPage'
    );
    render(
      <MemoryRouter>
        <KnowledgeBasesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('还没有知识库')).toBeInTheDocument();
    expect(screen.getByText('新建')).toBeInTheDocument();
  });
});

describe('AI 用例生成页面', () => {
  beforeEach(() => {
    mockMatchMedia();
    Object.defineProperty(globalThis, 'ResizeObserver', {
      configurable: true,
      value: TestResizeObserver,
    });
  });

  it('渲染生成入口与评审维度', async () => {
    const { default: AiCaseGenerationPage } = await import(
      '../pages/AiCaseGenerationPage'
    );
    render(
      <MemoryRouter>
        <AiCaseGenerationPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('AI 测试用例生成')).toBeInTheDocument();
    expect(screen.getByText('创建并生成测试点')).toBeInTheDocument();
    expect(screen.getByText('覆盖完整性')).toBeInTheDocument();
    expect(screen.getByText('快速生成')).toBeInTheDocument();
  });
});
