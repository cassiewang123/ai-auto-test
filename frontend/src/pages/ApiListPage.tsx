import { useEffect, useMemo, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Input,
  Tree,
  message,
  Empty,
  Badge,
  Select,
  Modal,
  Form,
  Popconfirm,
  Progress,
  Timeline,
  Spin,
  Segmented,
  Dropdown,
  Tooltip,
  Row,
  Col,
  Divider,
} from 'antd';
import {
  ApiOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  FolderOutlined,
  SearchOutlined,
  PlusOutlined,
  CopyOutlined,
  DeleteOutlined,
  DragOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  DownloadOutlined,
  FilterOutlined,
  EditOutlined,
  MoreOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ReactNode } from 'react';
import {
  testCaseApi,
  executionApi,
  projectApi,
  changeLogApi,
  historyApi,
} from '../services/api';
import type { CallHistoryRecord } from '../services/api';
import type { TestCase, Project, ProjectCreate, TestCaseCreate } from '../types';
import { useWorkspace } from '../contexts/WorkspaceContext';
import '../styles/api-workspace.css';

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
};

const statusBadge: Record<string, string> = {
  passed: '#52c41a',
  failed: '#ff4d4f',
  error: '#faad14',
};

const statusLabel: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  error: '错误',
  skipped: '跳过',
  queued: '排队中',
  running: '执行中',
  cancelled: '已取消',
};

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

interface TestCaseFormValues {
  title: string;
  method: string;
  url: string;
  group_path?: string;
  project_id?: string;
  headers?: string;
  params?: string;
  body?: string;
}

function hasContent(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

function formatJson(value: unknown): string {
  if (!hasContent(value)) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function ApiListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    projects: workspaceProjects,
    selectedProjectId: workspaceProjectId,
    setSelectedProjectId: setWorkspaceProjectId,
  } = useWorkspace();
  const [cases, setCases] = useState<TestCase[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [lastResults, setLastResults] = useState<Record<string, string>>({});
  const [recentResults, setRecentResults] = useState<Record<string, CallHistoryRecord>>({});
  const [queryProjectInitialized, setQueryProjectInitialized] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [projectForm] = Form.useForm<ProjectCreate>();

  // 行选择
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [batchExecuting, setBatchExecuting] = useState(false);
  const [batchResults, setBatchResults] = useState<{
    visible: boolean;
    total: number;
    passed: number;
    failed: number;
    error: number;
    results: any[];
  } | null>(null);

  // 新建用例
  const [caseModalOpen, setCaseModalOpen] = useState(false);
  const [creatingCase, setCreatingCase] = useState(false);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [caseForm] = Form.useForm<TestCaseFormValues>();

  // 移动到项目
  const [moveModalOpen, setMoveModalOpen] = useState(false);
  const [moveTargetId, setMoveTargetId] = useState<string>('');
  const [moving, setMoving] = useState(false);

  // 视图模式：表格 / 树形目录
  const [viewMode, setViewMode] = useState<'table' | 'tree'>('tree');
  const [methodFilter, setMethodFilter] = useState<string>('');
  const [groupFilter, setGroupFilter] = useState<string>('');
  // 树形视图选中的分组路径
  const [selectedGroupPath, setSelectedGroupPath] = useState<string>('');
  const [selectedCaseId, setSelectedCaseId] = useState<string>(
    () => searchParams.get('case_id') || ''
  );
  const [selectedTreeKey, setSelectedTreeKey] = useState<string>(
    () => searchParams.get('case_id') || ''
  );
  // 移动到分组（右键菜单）
  const [moveGroupModalOpen, setMoveGroupModalOpen] = useState(false);
  const [moveGroupSource, setMoveGroupSource] = useState<string>('');
  const [moveGroupTarget, setMoveGroupTarget] = useState<string>('');
  const [movingGroup, setMovingGroup] = useState(false);

  // 变更历史
  const [changeLogOpen, setChangeLogOpen] = useState(false);
  const [changeLogLoading, setChangeLogLoading] = useState(false);
  const [changeLogs, setChangeLogs] = useState<any[]>([]);

  const selectedProjectId = workspaceProjectId || '';

  // 首次进入时允许 URL 中的 project_id 覆盖已保存的工作区项目。
  useEffect(() => {
    if (queryProjectInitialized) return;
    const pid = searchParams.get('project_id');
    if (pid && pid !== workspaceProjectId) {
      setWorkspaceProjectId(pid);
    }
    setQueryProjectInitialized(true);
  }, [
    queryProjectInitialized,
    searchParams,
    setWorkspaceProjectId,
    workspaceProjectId,
  ]);

  // 顶部工作区切换项目时同步当前页面 URL，保留接口定位参数。
  useEffect(() => {
    if (!queryProjectInitialized) return;
    const currentProjectId = searchParams.get('project_id') || '';
    if (currentProjectId === selectedProjectId) return;

    const nextParams = new URLSearchParams(searchParams);
    if (selectedProjectId) {
      nextParams.set('project_id', selectedProjectId);
    } else {
      nextParams.delete('project_id');
    }
    nextParams.delete('case_id');
    setSearchParams(nextParams, { replace: true });
    setSelectedCaseId('');
    setSelectedTreeKey('');
  }, [
    queryProjectInitialized,
    searchParams,
    selectedProjectId,
    setSearchParams,
  ]);

  useEffect(() => {
    if (workspaceProjects.length > 0) {
      setProjects(workspaceProjects);
    }
  }, [workspaceProjects]);

  async function loadProjects() {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function loadData() {
    setLoading(true);
    try {
      const params: { page: number; page_size: number; project_id?: string } = {
        page: 1,
        page_size: 500,
      };
      if (selectedProjectId) params.project_id = selectedProjectId;
      const res = await testCaseApi.list(params);
      setCases(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecentResults() {
    try {
      const res = await historyApi.list({
        page: 1,
        page_size: 100,
        project_id: selectedProjectId || undefined,
      });
      const latestByCase: Record<string, CallHistoryRecord> = {};
      (res.data || []).forEach((record) => {
        if (record.test_case_id && !latestByCase[record.test_case_id]) {
          latestByCase[record.test_case_id] = record;
        }
      });
      setRecentResults(latestByCase);
    } catch {
      setRecentResults({});
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    loadData();
    loadRecentResults();
    setSelectedRowKeys([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  // 切换项目时更新 URL
  function handleProjectChange(value: string) {
    setWorkspaceProjectId(value || null);
  }

  const projectNameMap = useMemo(
    () => new Map(projects.map((project) => [project.id, project])),
    [projects]
  );

  const groupOptions = Array.from(
    new Set(cases.map((item) => item.group_path || '').filter(Boolean))
  ).sort((left, right) => left.localeCompare(right));

  const filtered = useMemo(
    () =>
      cases.filter((c) => {
        if (methodFilter && c.method !== methodFilter) return false;
        if (groupFilter && (c.group_path || '') !== groupFilter) return false;
        if (!search) return true;
        const s = search.toLowerCase();
        return (
          c.title.toLowerCase().includes(s) ||
          c.url.toLowerCase().includes(s) ||
          (c.group_path || '').toLowerCase().includes(s)
        );
      }),
    [cases, groupFilter, methodFilter, search]
  );

  const selectedCase = useMemo(
    () => filtered.find((item) => item.id === selectedCaseId) || filtered[0] || null,
    [filtered, selectedCaseId]
  );

  useEffect(() => {
    if (!selectedCase) {
      setSelectedTreeKey('');
      return;
    }
    if (!filtered.some((item) => item.id === selectedCaseId)) {
      setSelectedCaseId(selectedCase.id);
      setSelectedTreeKey(selectedCase.id);
    }
  }, [filtered, selectedCase, selectedCaseId]);

  function selectCase(record: TestCase) {
    setSelectedCaseId(record.id);
    setSelectedTreeKey(record.id);
    setSelectedGroupPath(record.group_path || '');
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('case_id', record.id);
    setSearchParams(nextParams, { replace: true });
  }

  function selectGroup(groupPath: string) {
    setSelectedGroupPath(groupPath);
    setSelectedTreeKey(`group::${groupPath}`);
    const groupCase = filtered.find((record) => {
      const recordPath = record.group_path || '';
      return groupPath
        ? recordPath === groupPath || recordPath.startsWith(`${groupPath}/`)
        : recordPath === '';
    });
    setSelectedCaseId(groupCase?.id || '');

    const nextParams = new URLSearchParams(searchParams);
    if (groupCase) {
      nextParams.set('case_id', groupCase.id);
    } else {
      nextParams.delete('case_id');
    }
    setSearchParams(nextParams, { replace: true });
  }

  function caseNode(c: TestCase): GroupTreeNode {
    return {
      title: (
        <Space>
          <Tag color={methodColor[c.method] || 'default'} style={{ margin: 0, minWidth: 50, textAlign: 'center' }}>
            {c.method}
          </Tag>
          <span>{c.title}</span>
          <span style={{ color: '#9ca3af', fontSize: 12 }}>{c.url}</span>
        </Space>
      ),
      key: c.id,
      isLeaf: true,
      caseData: c,
    };
  }

  // ---- 树形目录视图：从 group_path 解析多级分组树 ----
  interface GroupTreeNode {
    title: ReactNode;
    key: string;
    children?: GroupTreeNode[];
    isLeaf?: boolean;
    caseData?: TestCase;
  }

  // 构建 group_path 分层树
  function buildGroupTree(list: TestCase[]): GroupTreeNode[] {
    // 将 group_path 按 "/" 拆分，构建嵌套结构
    const root: Record<string, any> = {};
    const noGroup: TestCase[] = [];

    list.forEach((c) => {
      const gp = c.group_path;
      if (!gp) {
        noGroup.push(c);
        return;
      }
      const parts = gp.split('/').map((p) => p.trim()).filter(Boolean);
      let node = root;
      parts.forEach((part, idx) => {
        if (!node[part]) node[part] = { __cases: [], __children: {} };
        if (idx === parts.length - 1) {
          node[part].__cases.push(c);
        }
        node = node[part].__children;
      });
    });

    // 递归构建 Tree 节点
    function buildNodes(nodeMap: Record<string, any>, parentPath: string): GroupTreeNode[] {
      const nodes: GroupTreeNode[] = [];
      const entries = Object.entries(nodeMap).sort(([a], [b]) => a.localeCompare(b));
      for (const [name, val] of entries) {
        const fullPath = parentPath ? `${parentPath}/${name}` : name;
        const childNodes = buildNodes(val.__children || {}, fullPath);
        const caseCount = val.__cases?.length || 0;
        const totalCases = caseCount + countCasesInNodes(childNodes);
        nodes.push({
          title: (
            <Space>
              <FolderOutlined style={{ color: '#d97706' }} />
              <span style={{ fontWeight: 600 }}>{name}</span>
              <Badge count={totalCases} style={{ backgroundColor: '#e5e7eb', color: '#6b7280' }} />
            </Space>
          ),
          key: `group::${fullPath}`,
          children: [
            ...(val.__cases || []).map((c: TestCase) => caseNode(c)),
            ...childNodes,
          ],
        });
      }
      return nodes;
    }

    // 递归统计节点下所有用例数
    function countCasesInNodes(nodes: GroupTreeNode[]): number {
      let count = 0;
      nodes.forEach((n) => {
        if (n.caseData) count += 1;
        if (n.children) count += countCasesInNodes(n.children);
      });
      return count;
    }

    const result = buildNodes(root, '');
    // 添加未分组节点
    if (noGroup.length > 0) {
      result.push({
        title: (
          <Space>
            <FolderOutlined style={{ color: '#9ca3af' }} />
            <span style={{ fontWeight: 600 }}>未分组</span>
            <Badge count={noGroup.length} style={{ backgroundColor: '#e5e7eb', color: '#6b7280' }} />
          </Space>
        ),
        key: 'group::',
        children: noGroup.map((c) => caseNode(c)),
      });
    }
    return result;
  }

  const groupTreeData = buildGroupTree(filtered);

  // 右键菜单：移动到分组
  async function handleMoveGroup(sourcePath: string, targetPath: string) {
    // 找出该分组下的所有用例
    const casesToMove = cases.filter((c) => (c.group_path || '') === sourcePath);
    if (casesToMove.length === 0) {
      message.warning('该分组下没有接口');
      return;
    }
    setMovingGroup(true);
    try {
      // 逐个更新 group_path
      await Promise.all(
        casesToMove.map((c) =>
          testCaseApi.update(c.id, { group_path: targetPath || null })
        )
      );
      message.success(`已移动 ${casesToMove.length} 个接口到 "${targetPath || '未分组'}"`);
      setMoveGroupModalOpen(false);
      setMoveGroupTarget('');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setMovingGroup(false);
    }
  }

  // ---- 单个执行 ----
  async function handleQuickExecute(caseId: string) {
    setExecutingId(caseId);
    try {
      const res = await executionApi.runSavedCase(caseId);
      const status = res.data.status;
      setLastResults((prev) => ({ ...prev, [caseId]: status }));
      await loadRecentResults();
      if (status === 'passed') message.success('执行通过');
      else if (status === 'failed') message.warning('断言未通过');
      else message.error('执行出错');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setExecutingId(null);
    }
  }

  // ---- 批量执行 ----
  async function handleBatchExecute() {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选要执行的接口');
      return;
    }
    setBatchExecuting(true);
    try {
      const res = await testCaseApi.batchExecute(selectedRowKeys);
      const d = res.data;
      setLastResults((prev) => {
        const next = { ...prev };
        d.results.forEach((r: any) => {
          if (r.case_id) next[r.case_id] = r.status;
        });
        return next;
      });
      setBatchResults({
        visible: true,
        total: d.total,
        passed: d.passed,
        failed: d.failed,
        error: d.error,
        results: d.results,
      });
      await loadRecentResults();
      message.success(`批量执行完成: ${d.passed} 通过, ${d.failed} 失败, ${d.error} 错误`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBatchExecuting(false);
    }
  }

  // ---- 批量删除 ----
  async function handleBatchDelete() {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选要删除的接口');
      return;
    }
    try {
      const res = await testCaseApi.batchDelete(selectedRowKeys);
      message.success(`已删除 ${res.data.deleted} 个接口`);
      setSelectedRowKeys([]);
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // ---- 批量移动 ----
  async function handleBatchMove() {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选要移动的接口');
      return;
    }
    setMoveModalOpen(true);
  }

  async function confirmMove() {
    if (!moveTargetId) {
      message.warning('请选择目标项目');
      return;
    }
    setMoving(true);
    try {
      const targetId = moveTargetId === '__none__' ? null : moveTargetId;
      const res = await testCaseApi.batchMove(selectedRowKeys, targetId as string | null);
      message.success(`已移动 ${res.data.moved} 个接口`);
      setMoveModalOpen(false);
      setSelectedRowKeys([]);
      setMoveTargetId('');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setMoving(false);
    }
  }

  // ---- 单个复制 ----
  async function handleCopy(caseId: string) {
    try {
      const res = await testCaseApi.copy(caseId);
      message.success('复制成功');
      await loadData();
      if (res.data) {
        selectCase(res.data);
      }
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // ---- 单个删除 ----
  async function handleDelete(caseId: string) {
    try {
      await testCaseApi.delete(caseId);
      message.success('删除成功');
      if (selectedCaseId === caseId) {
        setSelectedCaseId('');
        setSelectedTreeKey('');
      }
      await loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // ---- 新建项目 ----
  async function handleCreateProject() {
    try {
      const values = await projectForm.validateFields();
      setCreatingProject(true);
      const res = await projectApi.create(values);
      message.success('项目创建成功');
      setProjectModalOpen(false);
      projectForm.resetFields();
      await loadProjects();
      setWorkspaceProjectId(res.data.id);
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setCreatingProject(false);
    }
  }

  function openCreateCase() {
    setEditingCase(null);
    caseForm.resetFields();
    caseForm.setFieldsValue({
      method: 'GET',
      project_id: selectedProjectId || undefined,
    });
    setCaseModalOpen(true);
  }

  function openEditCase(record: TestCase) {
    setEditingCase(record);
    caseForm.setFieldsValue({
      title: record.title,
      method: record.method,
      url: record.url,
      group_path: record.group_path || '',
      project_id: record.project_id,
      headers: formatJson(record.headers),
      params: formatJson(record.params),
      body: formatJson(record.body),
    });
    setCaseModalOpen(true);
  }

  // ---- 新建/编辑用例 ----
  async function handleSaveCase() {
    try {
      const values = await caseForm.validateFields();
      setCreatingCase(true);
      const payload: TestCaseCreate = {
        title: values.title,
        method: values.method,
        url: values.url,
        headers: values.headers ? JSON.parse(values.headers as string) : {},
        params: values.params ? JSON.parse(values.params as string) : {},
        body: values.body ? JSON.parse(values.body as string) : undefined,
        group_path: values.group_path || '',
        project_id: values.project_id || selectedProjectId || undefined,
        markers: [],
        assertions: [
          {
            assertion_type: 'status_code',
            operator: 'eq',
            expected: '200',
            priority: 'P0',
            order: 0,
          },
        ],
      };
      const res = editingCase
        ? await testCaseApi.update(editingCase.id, payload)
        : await testCaseApi.create(payload);
      message.success(editingCase ? '接口更新成功' : '用例创建成功');
      setCaseModalOpen(false);
      setEditingCase(null);
      caseForm.resetFields();
      await loadData();
      if (res.data) {
        selectCase(res.data);
      }
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setCreatingCase(false);
    }
  }

  // ---- 变更历史 ----
  async function openChangeLog(caseId: string) {
    setChangeLogOpen(true);
    setChangeLogLoading(true);
    setChangeLogs([]);
    try {
      const res = await changeLogApi.getByCaseId(caseId);
      setChangeLogs(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setChangeLogLoading(false);
    }
  }

  // ---- 下载接口文档 ----
  async function handleDownloadDoc(caseId: string) {
    try {
      await testCaseApi.downloadDoc(caseId);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  function openDebugger(record: TestCase) {
    const params = new URLSearchParams({
      method: record.method,
      url: record.url,
      headers: JSON.stringify(record.headers || {}),
      params: JSON.stringify(record.params || {}),
    });
    if (record.body !== undefined && record.body !== null) {
      params.set('body', JSON.stringify(record.body));
    }
    if (record.title) params.set('title', record.title);
    navigate(`/quick-test?${params.toString()}`);
  }

  const renderActions = (c: TestCase) => (
    <Space size={2}>
      <Tooltip title="打开调试">
        <Button
          size="small"
          type="text"
          icon={<ThunderboltOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            openDebugger(c);
          }}
        />
      </Tooltip>
      <Tooltip title="执行">
        <Button
          size="small"
          type="text"
          icon={<PlayCircleOutlined />}
          loading={executingId === c.id}
          onClick={(e) => {
            e.stopPropagation();
            handleQuickExecute(c.id);
          }}
        />
      </Tooltip>
      <Tooltip title="编辑">
        <Button
          size="small"
          type="text"
          icon={<EditOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            openEditCase(c);
          }}
        />
      </Tooltip>
      <Tooltip title="复制">
        <Button
          size="small"
          type="text"
          icon={<CopyOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            handleCopy(c.id);
          }}
        />
      </Tooltip>
      <Tooltip title="修改历史">
        <Button
          size="small"
          type="text"
          icon={<HistoryOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            openChangeLog(c.id);
          }}
        />
      </Tooltip>
      <Dropdown
        trigger={['click']}
        menu={{
          items: [
            {
              key: 'download',
              icon: <DownloadOutlined />,
              label: '下载文档',
              onClick: () => void handleDownloadDoc(c.id),
            },
            {
              key: 'delete',
              icon: <DeleteOutlined />,
              label: '删除',
              danger: true,
              onClick: () => {
                Modal.confirm({
                  title: '确认删除该接口？',
                  content: c.title,
                  okText: '删除',
                  okButtonProps: { danger: true },
                  cancelText: '取消',
                  onOk: () => handleDelete(c.id),
                });
              },
            },
          ],
        }}
      >
        <Tooltip title="更多">
          <Button
            size="small"
            type="text"
            icon={<MoreOutlined />}
            onClick={(e) => e.stopPropagation()}
          />
        </Tooltip>
      </Dropdown>
    </Space>
  );

  // 批量操作工具栏
  const batchToolbar = selectedRowKeys.length > 0 && (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 12px',
        background: '#f8fafc',
        border: '1px solid #dbeafe',
        borderRadius: 6,
        marginBottom: 12,
      }}
    >
      <span style={{ fontWeight: 600, color: '#1e40af' }}>
        已选中 {selectedRowKeys.length} 个接口
      </span>
      <Button
        type="primary"
        icon={<ThunderboltOutlined />}
        loading={batchExecuting}
        onClick={handleBatchExecute}
      >
        批量执行
      </Button>
      <Button icon={<DragOutlined />} onClick={handleBatchMove}>
        移动到项目
      </Button>
      <Popconfirm
        title={`确认删除选中的 ${selectedRowKeys.length} 个接口？`}
        onConfirm={handleBatchDelete}
      >
        <Button danger icon={<DeleteOutlined />}>
          批量删除
        </Button>
      </Popconfirm>
      <Button type="link" onClick={() => setSelectedRowKeys([])}>
        取消选择
      </Button>
    </div>
  );

  const selectedRecentResult = selectedCase
    ? recentResults[selectedCase.id]
    : undefined;
  const selectedExecutionStatus = selectedCase
    ? lastResults[selectedCase.id] || selectedRecentResult?.status
    : undefined;

  function renderDataSection(title: string, value: unknown, emptyText: string) {
    return (
      <section className="api-detail-section">
        <div className="api-detail-section-title">{title}</div>
        {hasContent(value) ? (
          <pre className="api-json-preview">{formatJson(value)}</pre>
        ) : (
          <div className="api-detail-empty">{emptyText}</div>
        )}
      </section>
    );
  }

  return (
    <div className="api-list-page">
      <Card
        title={
          <Space>
            <ApiOutlined />
            <span>API 接口</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {cases.length} 个接口
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<PlusOutlined />} onClick={() => setProjectModalOpen(true)}>
              新建项目
            </Button>
            <Button onClick={() => navigate('/import')}>导入</Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreateCase}
            >
              新建用例
            </Button>
          </Space>
        }
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: 16,
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Space wrap>
            <Select
              value={selectedProjectId}
              onChange={handleProjectChange}
              style={{ width: 210 }}
              placeholder="全部项目"
              showSearch
              optionFilterProp="label"
              options={[
                { value: '', label: '全部项目' },
                ...projects.map((p) => ({ value: p.id, label: p.name })),
              ]}
            />
            <Select
              value={methodFilter}
              onChange={setMethodFilter}
              style={{ width: 130 }}
              suffixIcon={<FilterOutlined />}
              options={[
                { value: '', label: '全部方法' },
                ...METHODS.map((method) => ({ value: method, label: method })),
              ]}
            />
            <Select
              value={groupFilter}
              onChange={setGroupFilter}
              style={{ width: 180 }}
              suffixIcon={<FilterOutlined />}
              options={[
                { value: '', label: '全部分组' },
                ...groupOptions.map((group) => ({ value: group, label: group })),
              ]}
            />
            <Input
              placeholder="搜索名称、URL、分组"
              allowClear
              style={{ width: 260 }}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              prefix={<SearchOutlined />}
            />
          </Space>
          <Space wrap>
            <Segmented
              value={viewMode}
              onChange={(v) => setViewMode(v as 'table' | 'tree')}
              options={[
                { label: '列表', value: 'table' },
                { label: '工作台', value: 'tree' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          </Space>
        </div>

        <div
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'center',
            flexWrap: 'wrap',
            marginBottom: 12,
            minHeight: 24,
          }}
        >
          <span style={{ color: '#6b7280', fontSize: 13 }}>
            当前显示 {filtered.length} 个
          </span>
          {METHODS.map((method) => {
            const count = filtered.filter((item) => item.method === method).length;
            return count > 0 ? (
              <Tag key={method} color={methodColor[method]}>
                {method} {count}
              </Tag>
            ) : null;
          })}
        </div>

        {batchToolbar}

        {viewMode === 'table' && (
          filtered.length === 0 ? (
            <Empty description="暂无接口，请新建或导入接口" style={{ padding: 40 }}>
              <Space>
                <Button type="primary" onClick={openCreateCase}>
                  新建用例
                </Button>
                <Button onClick={() => navigate('/import')}>导入接口</Button>
              </Space>
            </Empty>
          ) : (
            <Table
              dataSource={filtered}
              rowKey="id"
              loading={loading}
              size="middle"
              rowSelection={{
                selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys(keys as string[]),
              }}
              onRow={(record) => ({
                onClick: () => selectCase(record),
              })}
              pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
              columns={[
                {
                  title: '方法',
                  dataIndex: 'method',
                  width: 78,
                  render: (method: string) => (
                    <Tag color={methodColor[method] || 'default'}>{method}</Tag>
                  ),
                },
                {
                  title: '接口',
                  dataIndex: 'title',
                  ellipsis: true,
                  render: (title: string, record) => (
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{title}</div>
                      <div
                        style={{
                          color: '#6b7280',
                          fontFamily: 'monospace',
                          fontSize: 12,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {record.url}
                      </div>
                    </div>
                  ),
                },
                {
                  title: '分组',
                  dataIndex: 'group_path',
                  width: 150,
                  ellipsis: true,
                  render: (value: string) => value || <span style={{ color: '#9ca3af' }}>未分组</span>,
                },
                {
                  title: '项目',
                  dataIndex: 'project_id',
                  width: 150,
                  ellipsis: true,
                  render: (projectId: string) =>
                    projectId ? projectNameMap.get(projectId)?.name || projectId : '未分类',
                },
                {
                  title: '标记',
                  dataIndex: 'markers',
                  width: 150,
                  render: (markers: string[]) =>
                    (markers || []).slice(0, 2).map((marker) => (
                      <Tag key={marker}>{marker}</Tag>
                    )),
                },
                {
                  title: '最近执行',
                  width: 100,
                  render: (_, record) => {
                    const status =
                      lastResults[record.id] || recentResults[record.id]?.status;
                    return status ? (
                      <Badge
                        color={statusBadge[status] || '#d9d9d9'}
                        text={statusLabel[status] || status}
                      />
                    ) : <span style={{ color: '#9ca3af' }}>未执行</span>;
                  },
                },
                {
                  title: '操作',
                  width: 210,
                  align: 'right',
                  render: (_, record) => renderActions(record),
                },
              ]}
            />
          )
        )}

        {viewMode === 'tree' && (
          groupTreeData.length === 0 ? (
            <Empty description="暂无接口，请新建或导入接口" style={{ padding: 40 }}>
              <Space>
                <Button type="primary" onClick={openCreateCase}>
                  新建用例
                </Button>
                <Button onClick={() => navigate('/import')}>导入接口</Button>
              </Space>
            </Empty>
          ) : (
            <div className="api-workspace">
              <aside className="api-workspace-sidebar">
                <div className="api-workspace-sidebar-header">
                  <div>
                    <div className="api-workspace-sidebar-title">
                      <FolderOutlined />
                      <span>接口资产</span>
                    </div>
                    <div className="api-workspace-sidebar-caption">
                      {selectedGroupPath || '全部分组'} · {filtered.length} 个接口
                    </div>
                  </div>
                  <Tooltip title="右键分组可批量移动">
                    <Button type="text" size="small" icon={<MoreOutlined />} />
                  </Tooltip>
                </div>
                <Tree
                  className="api-asset-tree"
                  treeData={groupTreeData}
                  defaultExpandAll
                  showLine
                  blockNode
                  selectedKeys={[
                    selectedTreeKey || selectedCase?.id || '',
                  ].filter(Boolean)}
                  onSelect={(keys) => {
                    const key = String(keys[0] || '');
                    if (!key) return;
                    if (key.startsWith('group::')) {
                      selectGroup(key.replace('group::', ''));
                      return;
                    }
                    const record = filtered.find((item) => item.id === key);
                    if (record) selectCase(record);
                  }}
                  titleRender={(node) => {
                    if (
                      typeof node.key === 'string' &&
                      node.key.startsWith('group::') &&
                      !node.caseData
                    ) {
                      const groupPath = node.key.replace('group::', '');
                      return (
                        <Dropdown
                          trigger={['contextMenu']}
                          menu={{
                            items: [
                              {
                                key: 'move',
                                label: '移动到分组...',
                                onClick: () => {
                                  setMoveGroupSource(groupPath);
                                  setMoveGroupTarget('');
                                  setMoveGroupModalOpen(true);
                                },
                              },
                              {
                                key: 'select',
                                label: '查看此分组',
                                onClick: () => selectGroup(groupPath),
                              },
                            ],
                          }}
                        >
                          <span className="api-tree-folder">{node.title}</span>
                        </Dropdown>
                      );
                    }
                    if (node.caseData) {
                      const record = node.caseData;
                      const status =
                        lastResults[record.id] ||
                        recentResults[record.id]?.status;
                      return (
                        <div className="api-tree-case" title={`${record.title}\n${record.url}`}>
                          <Tag
                            color={methodColor[record.method] || 'default'}
                            className="api-tree-method"
                          >
                            {record.method}
                          </Tag>
                          <span className="api-tree-case-name">{record.title}</span>
                          {status && (
                            <Badge
                              color={statusBadge[status] || '#d9d9d9'}
                              className="api-tree-status"
                            />
                          )}
                        </div>
                      );
                    }
                    return node.title;
                  }}
                />
              </aside>

              <main className="api-workspace-detail">
                {selectedCase ? (
                  <>
                    <div className="api-detail-header">
                      <div className="api-detail-heading">
                        <div className="api-detail-context">
                          {projectNameMap.get(selectedCase.project_id || '')?.name ||
                            '未分类项目'}
                          <span>/</span>
                          {selectedCase.group_path || '未分组'}
                        </div>
                        <h2>{selectedCase.title}</h2>
                        <div className="api-detail-endpoint">
                          <Tag
                            color={methodColor[selectedCase.method] || 'default'}
                            className="api-detail-method"
                          >
                            {selectedCase.method}
                          </Tag>
                          <code>{selectedCase.url}</code>
                        </div>
                      </div>
                      <Space wrap className="api-detail-actions">
                        <Button
                          type="primary"
                          icon={<ThunderboltOutlined />}
                          onClick={() => openDebugger(selectedCase)}
                        >
                          调试
                        </Button>
                        <Button
                          icon={<PlayCircleOutlined />}
                          loading={executingId === selectedCase.id}
                          onClick={() => handleQuickExecute(selectedCase.id)}
                        >
                          执行
                        </Button>
                        <Button
                          icon={<EditOutlined />}
                          onClick={() => openEditCase(selectedCase)}
                        >
                          编辑
                        </Button>
                        <Button
                          icon={<CopyOutlined />}
                          onClick={() => handleCopy(selectedCase.id)}
                        >
                          复制
                        </Button>
                        <Button
                          icon={<HistoryOutlined />}
                          onClick={() => openChangeLog(selectedCase.id)}
                        >
                          历史
                        </Button>
                        <Dropdown
                          menu={{
                            items: [
                              {
                                key: 'download',
                                icon: <DownloadOutlined />,
                                label: '下载接口文档',
                                onClick: () =>
                                  void handleDownloadDoc(selectedCase.id),
                              },
                              {
                                key: 'delete',
                                icon: <DeleteOutlined />,
                                label: '删除接口',
                                danger: true,
                                onClick: () => {
                                  Modal.confirm({
                                    title: '确认删除该接口？',
                                    content: selectedCase.title,
                                    okText: '删除',
                                    okButtonProps: { danger: true },
                                    cancelText: '取消',
                                    onOk: () => handleDelete(selectedCase.id),
                                  });
                                },
                              },
                            ],
                          }}
                        >
                          <Button icon={<MoreOutlined />} aria-label="更多操作" />
                        </Dropdown>
                      </Space>
                    </div>

                    <div className="api-execution-strip">
                      <div>
                        <span className="api-execution-label">最近执行</span>
                        {selectedExecutionStatus ? (
                          <Badge
                            color={
                              statusBadge[selectedExecutionStatus] || '#d9d9d9'
                            }
                            text={
                              statusLabel[selectedExecutionStatus] ||
                              selectedExecutionStatus
                            }
                          />
                        ) : (
                          <span className="api-detail-empty">尚未执行</span>
                        )}
                      </div>
                      <div>
                        <span className="api-execution-label">HTTP 状态</span>
                        <strong>
                          {selectedRecentResult?.status_code ?? '--'}
                        </strong>
                      </div>
                      <div>
                        <span className="api-execution-label">耗时</span>
                        <strong>
                          {selectedRecentResult
                            ? `${Math.round(selectedRecentResult.duration * 1000)} ms`
                            : '--'}
                        </strong>
                      </div>
                      <div>
                        <span className="api-execution-label">执行时间</span>
                        <strong>
                          {selectedRecentResult?.executed_at
                            ? new Date(
                                selectedRecentResult.executed_at
                              ).toLocaleString('zh-CN')
                            : '--'}
                        </strong>
                      </div>
                    </div>

                    <div className="api-detail-meta">
                      <div>
                        <span>状态</span>
                        <Tag color={selectedCase.is_active ? 'green' : 'default'}>
                          {selectedCase.is_active ? '启用' : '停用'}
                        </Tag>
                      </div>
                      <div>
                        <span>断言</span>
                        <strong>{selectedCase.assertions?.length || 0} 条</strong>
                      </div>
                      <div>
                        <span>重试</span>
                        <strong>{selectedCase.retry_count || 0} 次</strong>
                      </div>
                      <div>
                        <span>更新时间</span>
                        <strong>
                          {selectedCase.updated_at
                            ? new Date(selectedCase.updated_at).toLocaleString(
                                'zh-CN'
                              )
                            : '--'}
                        </strong>
                      </div>
                    </div>

                    {selectedCase.description && (
                      <section className="api-detail-section">
                        <div className="api-detail-section-title">说明</div>
                        <div className="api-detail-description">
                          {selectedCase.description}
                        </div>
                      </section>
                    )}

                    <Divider />
                    <div className="api-payload-grid">
                      {renderDataSection(
                        '请求头',
                        selectedCase.headers,
                        '未配置请求头'
                      )}
                      {renderDataSection(
                        '查询参数',
                        selectedCase.params,
                        '未配置查询参数'
                      )}
                      {renderDataSection(
                        '请求体',
                        selectedCase.body,
                        '当前请求没有请求体'
                      )}
                      {renderDataSection(
                        '提取规则',
                        selectedCase.extract_rules,
                        '未配置变量提取'
                      )}
                    </div>
                  </>
                ) : (
                  <Empty
                    description="从左侧选择一个接口查看详情"
                    className="api-workspace-empty"
                  />
                )}
              </main>
            </div>
          )
        )}
      </Card>

      {/* 新建项目 Modal */}
      <Modal
        title="新建项目"
        open={projectModalOpen}
        onOk={handleCreateProject}
        confirmLoading={creatingProject}
        onCancel={() => setProjectModalOpen(false)}
        destroyOnHidden
      >
        <Form form={projectForm} layout="vertical">
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="如：用户中心" />
          </Form.Item>
          <Form.Item name="code" label="项目标识">
            <Input placeholder="如：user-center（可选）" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="如：http://robin.ep.local:30080" />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea rows={3} placeholder="项目描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新建/编辑用例 Modal */}
      <Modal
        title={editingCase ? '编辑接口' : '新建测试用例'}
        open={caseModalOpen}
        onOk={handleSaveCase}
        confirmLoading={creatingCase}
        onCancel={() => {
          setCaseModalOpen(false);
          setEditingCase(null);
        }}
        width={640}
        destroyOnHidden
      >
        <Form form={caseForm} layout="vertical" initialValues={{ method: 'GET' }}>
          <Form.Item
            name="title"
            label="用例标题"
            rules={[{ required: true, message: '请输入用例标题' }]}
          >
            <Input placeholder="如：获取用户列表" />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} sm={6}>
              <Form.Item name="method" label="请求方法" rules={[{ required: true }]}>
                <Select options={METHODS.map((m) => ({ label: m, value: m }))} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={18}>
              <Form.Item
                name="url"
                label="请求 URL"
                rules={[{ required: true, message: '请输入请求 URL' }]}
              >
                <Input placeholder="http://api.example.com/users" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="group_path" label="分组路径">
            <Input placeholder="如：用户管理（可选）" />
          </Form.Item>
          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
          <Form.Item name="headers" label="Headers (JSON)">
            <Input.TextArea rows={2} placeholder='{"Content-Type": "application/json"}' />
          </Form.Item>
          <Form.Item name="params" label="Query Params (JSON)">
            <Input.TextArea rows={2} placeholder='{"page": 1}' />
          </Form.Item>
          <Form.Item name="body" label="Body (JSON)">
            <Input.TextArea rows={3} placeholder='{"name": "test"}' />
          </Form.Item>
        </Form>
      </Modal>

      {/* 移动到项目 Modal */}
      <Modal
        title={`移动 ${selectedRowKeys.length} 个接口到项目`}
        open={moveModalOpen}
        onOk={confirmMove}
        confirmLoading={moving}
        onCancel={() => setMoveModalOpen(false)}
        destroyOnHidden
      >
        <div style={{ marginBottom: 12, color: '#6b7280' }}>
          选择目标项目，选中的接口将移动到该项目下。
        </div>
        <Select
          value={moveTargetId}
          onChange={setMoveTargetId}
          style={{ width: '100%' }}
          placeholder="选择目标项目"
          showSearch
          optionFilterProp="label"
          options={[
            { value: '__none__', label: '移出项目（变为未分类）' },
            ...projects.map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
      </Modal>

      {/* 批量执行结果 Modal */}
      <Modal
        title="批量执行结果"
        open={batchResults?.visible || false}
        onCancel={() => setBatchResults(null)}
        footer={<Button type="primary" onClick={() => setBatchResults(null)}>关闭</Button>}
        width={720}
      >
        {batchResults && (
          <div>
            <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 28, fontWeight: 700 }}>{batchResults.total}</div>
                <div style={{ color: '#6b7280' }}>总计</div>
              </div>
              <div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#52c41a' }}>{batchResults.passed}</div>
                <div style={{ color: '#6b7280' }}>通过</div>
              </div>
              <div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#ff4d4f' }}>{batchResults.failed}</div>
                <div style={{ color: '#6b7280' }}>失败</div>
              </div>
              <div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#faad14' }}>{batchResults.error}</div>
                <div style={{ color: '#6b7280' }}>错误</div>
              </div>
              <div style={{ flex: 1 }}>
                <Progress
                  percent={batchResults.total > 0 ? Math.round((batchResults.passed / batchResults.total) * 100) : 0}
                  strokeColor="#52c41a"
                  format={(p) => `${p}%`}
                />
              </div>
            </div>
            <Table
              dataSource={batchResults.results}
              rowKey="case_id"
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 80,
                  render: (s: string) => (
                    <Badge color={statusBadge[s] || '#d9d9d9'} text={statusLabel[s] || s} />
                  ),
                },
                { title: '标题', dataIndex: 'title', ellipsis: true },
                {
                  title: '方法',
                  dataIndex: 'method',
                  width: 70,
                  render: (m: string) => m ? <Tag color={methodColor[m] || 'default'}>{m}</Tag> : '-',
                },
                { title: '状态码', dataIndex: 'status_code', width: 80 },
                {
                  title: '耗时(s)',
                  dataIndex: 'duration',
                  width: 80,
                  render: (d: number) => d ? d.toFixed(3) : '-',
                },
                {
                  title: '错误',
                  dataIndex: 'error',
                  ellipsis: true,
                  render: (e: string) => e ? <span style={{ color: '#ff4d4f' }}>{e}</span> : '-',
                },
              ]}
            />
          </div>
        )}
      </Modal>

      {/* 修改历史 Modal */}
      <Modal
        title="接口变更历史"
        open={changeLogOpen}
        onCancel={() => setChangeLogOpen(false)}
        footer={<Button type="primary" onClick={() => setChangeLogOpen(false)}>关闭</Button>}
        width={640}
        destroyOnHidden
      >
        {changeLogLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin description="加载中..." />
          </div>
        ) : changeLogs.length === 0 ? (
          <Empty description="暂无变更历史" />
        ) : (
          <Timeline
            items={changeLogs.map((log: any) => {
              const op = log.operation || log.action || log.op_type || 'updated';
              const opColorMap: Record<string, string> = {
                created: 'green',
                updated: 'blue',
                deleted: 'red',
              };
              const opLabelMap: Record<string, string> = {
                created: '创建',
                updated: '更新',
                deleted: '删除',
              };
              const time = log.created_at || log.changed_at || log.updated_at || log.time;
              const fields =
                log.changed_fields || log.fields || log.changes || log.diff;
              return {
                color: opColorMap[op] || 'blue',
                children: (
                  <div>
                    <div style={{ fontWeight: 600 }}>
                      <Tag color={opColorMap[op] || 'blue'}>
                        {opLabelMap[op] || op}
                      </Tag>
                      {time ? new Date(time).toLocaleString('zh-CN') : ''}
                    </div>
                    {log.operator && (
                      <div style={{ color: '#6b7280', fontSize: 12, marginTop: 4 }}>
                        操作人：{log.operator}
                      </div>
                    )}
                    {fields && (
                      <div style={{ marginTop: 4, fontSize: 13 }}>
                        {typeof fields === 'string' ? (
                          <span>{fields}</span>
                        ) : Array.isArray(fields) ? (
                          fields.map((f: any, i: number) => (
                            <Tag key={i} style={{ marginBottom: 4 }}>
                              {typeof f === 'string' ? f : JSON.stringify(f)}
                            </Tag>
                          ))
                        ) : (
                          Object.entries(fields).map(([k, v]: [string, any]) => (
                            <div key={k} style={{ marginBottom: 2 }}>
                              <span style={{ color: '#6b7280' }}>{k}：</span>
                              <span>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                    {log.description && (
                      <div style={{ marginTop: 4, color: '#374151', fontSize: 13 }}>
                        {log.description}
                      </div>
                    )}
                  </div>
                ),
              };
            })}
          />
        )}
      </Modal>

      {/* 移动到分组 Modal（目录树视图右键菜单） */}
      <Modal
        title={`移动分组 "${moveGroupSource || '未分组'}" 到新分组`}
        open={moveGroupModalOpen}
        onOk={() => handleMoveGroup(moveGroupSource, moveGroupTarget)}
        confirmLoading={movingGroup}
        onCancel={() => {
          setMoveGroupModalOpen(false);
          setMoveGroupTarget('');
        }}
        destroyOnHidden
      >
        <div style={{ marginBottom: 12, color: '#6b7280' }}>
          该分组下的所有接口将被移动到新的分组路径。输入新的分组路径（如“用户管理/认证”），留空则移到未分组。
        </div>
        <Input
          value={moveGroupTarget}
          onChange={(e) => setMoveGroupTarget(e.target.value)}
          placeholder="如：用户管理/认证（留空则移到未分组）"
        />
      </Modal>
    </div>
  );
}
