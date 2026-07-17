import { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Input,
  Select,
  Modal,
  Form,
  message,
  Popconfirm,
  Badge,
  Empty,
  Progress,
  Timeline,
  Spin,
  Tabs,
  Switch,
  Alert,
  InputNumber,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  CopyOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  EditOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  ThunderboltOutlined,
  DragOutlined,
  FolderOutlined,
  SearchOutlined,
  HistoryOutlined,
  DownloadOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { testCaseApi, executionApi, projectApi, changeLogApi, dbAssertionApi, environmentApi } from '../services/api';
import type { TestCase, Project, TestCaseCreate, Environment } from '../types';

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
};
const statusBadge: Record<string, string> = {
  passed: '#52c41a', failed: '#ff4d4f', error: '#faad14',
};
const statusLabel: Record<string, string> = {
  passed: '通过', failed: '失败', error: '错误',
};
const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

export default function TestCasesPage() {
  const [cases, setCases] = useState<TestCase[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [selectedGroup, setSelectedGroup] = useState<string>('');
  const [urlSearch, setUrlSearch] = useState('');
  const [titleSearch, setTitleSearch] = useState('');

  // 行选择
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [lastResults, setLastResults] = useState<Record<string, string>>({});
  const [batchExecuting, setBatchExecuting] = useState(false);
  const [batchResults, setBatchResults] = useState<{
    visible: boolean;
    total: number; passed: number; failed: number; error: number;
    results: any[];
  } | null>(null);

  // 新建/编辑
  const [caseModalOpen, setCaseModalOpen] = useState(false);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 移动到项目
  const [moveModalOpen, setMoveModalOpen] = useState(false);
  const [moveTargetId, setMoveTargetId] = useState('');
  const [moving, setMoving] = useState(false);

  // 变更历史
  const [changeLogOpen, setChangeLogOpen] = useState(false);
  const [changeLogLoading, setChangeLogLoading] = useState(false);
  const [changeLogs, setChangeLogs] = useState<any[]>([]);

  // 数据库断言
  const [dbAssertions, setDbAssertions] = useState<any[]>([]);
  const [dbAssertionLoading, setDbAssertionLoading] = useState(false);
  const [assertionModalOpen, setAssertionModalOpen] = useState(false);
  const [editingAssertion, setEditingAssertion] = useState<any | null>(null);
  const [assertionSaving, setAssertionSaving] = useState(false);
  const [assertionForm] = Form.useForm();
  // 环境列表（用于断言测试）
  const [envList, setEnvList] = useState<Environment[]>([]);
  const [testEnvId, setTestEnvId] = useState<string>('');
  const [testingAssertion, setTestingAssertion] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  // 用例 Modal 当前激活 Tab
  const [caseModalTab, setCaseModalTab] = useState('basic');

  // DB 断言操作符选项
  const DB_OPERATORS = [
    { label: 'count (行数等于)', value: 'count' },
    { label: 'exists (字段存在)', value: 'exists' },
    { label: 'equals (等于)', value: 'equals' },
    { label: 'contains (包含)', value: 'contains' },
    { label: 'greater_than (大于)', value: 'greater_than' },
    { label: 'less_than (小于)', value: 'less_than' },
  ];

  const loadProjects = useCallback(async () => {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { page: 1, page_size: 100 };
      if (selectedProjectId) params.project_id = selectedProjectId;
      if (selectedGroup) params.group_path = selectedGroup;
      if (urlSearch) params.url_search = urlSearch;
      if (titleSearch) params.title_search = titleSearch;
      const res = await testCaseApi.list(params);
      setCases(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, selectedGroup, urlSearch, titleSearch]);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => { loadData(); setSelectedRowKeys([]); }, [loadData]);

  // 获取当前项目的所有模块（分组）
  const moduleOptions = Array.from(new Set(cases.map(c => c.group_path).filter(Boolean))) as string[];

  const projectNameMap = new Map<string, Project>();
  projects.forEach(p => projectNameMap.set(p.id, p));

  // ---- 执行 ----
  async function handleExecute(caseId: string) {
    setExecutingId(caseId);
    try {
      const res = await executionApi.runSavedCase(caseId);
      const status = res.data.status;
      setLastResults(prev => ({ ...prev, [caseId]: status }));
      if (status === 'passed') message.success('执行通过');
      else if (status === 'failed') message.warning('断言未通过');
      else message.error('执行出错');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setExecutingId(null);
    }
  }

  async function handleBatchExecute(caseIds?: string[]) {
    const ids = caseIds || selectedRowKeys;
    if (ids.length === 0) { message.warning('请先勾选用例'); return; }
    setBatchExecuting(true);
    try {
      const res = await testCaseApi.batchExecute(ids);
      const d = res.data;
      setLastResults(prev => {
        const next = { ...prev };
        d.results.forEach((r: any) => { if (r.case_id) next[r.case_id] = r.status; });
        return next;
      });
      setBatchResults({ visible: true, ...d });
      message.success(`批量执行: ${d.passed}通过, ${d.failed}失败, ${d.error}错误`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBatchExecuting(false);
    }
  }

  // ---- 复制 ----
  async function handleCopy(caseId: string) {
    try {
      await testCaseApi.copy(caseId);
      message.success('复制成功');
      loadData();
    } catch (e: any) { message.error(e.message); }
  }

  // ---- 删除 ----
  async function handleDelete(caseId: string) {
    try {
      await testCaseApi.delete(caseId);
      message.success('删除成功');
      loadData();
    } catch (e: any) { message.error(e.message); }
  }

  async function handleBatchDelete() {
    if (selectedRowKeys.length === 0) { message.warning('请先勾选用例'); return; }
    try {
      const res = await testCaseApi.batchDelete(selectedRowKeys);
      message.success(`已删除 ${res.data.deleted} 个用例`);
      setSelectedRowKeys([]);
      loadData();
    } catch (e: any) { message.error(e.message); }
  }

  // ---- 排序 ----
  async function handleMove(caseId: string, direction: 'up' | 'down') {
    const currentIndex = cases.findIndex(c => c.id === caseId);
    if (currentIndex < 0) return;
    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= cases.length) return;

    // 交换顺序
    const newCases = [...cases];
    [newCases[currentIndex], newCases[targetIndex]] = [newCases[targetIndex], newCases[currentIndex]];

    // 提取有序 ID 列表并调用 reorder
    const orderedIds = newCases.map(c => c.id);
    try {
      await testCaseApi.reorder(orderedIds);
      setCases(newCases);
      message.success('排序已更新');
    } catch (e: any) { message.error(e.message); }
  }

  // ---- 新建/编辑 ----
  function openCreate() {
    setEditingCase(null);
    form.resetFields();
    form.setFieldsValue({
      method: 'GET',
      headers: '{\n  "Content-Type": "application/json"\n}',
      params: '{}',
      group_path: '',
      retry_count: 0,
      retry_interval: 1.0,
      pre_script: '',
      post_script: '',
    });
    setDbAssertions([]);
    setCaseModalTab('basic');
    setCaseModalOpen(true);
  }

  function openEdit(record: TestCase) {
    setEditingCase(record);
    form.setFieldsValue({
      title: record.title,
      method: record.method,
      url: record.url,
      group_path: record.group_path || '',
      project_id: record.project_id,
      headers: JSON.stringify(record.headers || {}, null, 2),
      params: JSON.stringify(record.params || {}, null, 2),
      body: record.body ? JSON.stringify(record.body, null, 2) : '',
      retry_count: record.retry_count ?? 0,
      retry_interval: record.retry_interval ?? 1.0,
      pre_script: record.pre_script || '',
      post_script: record.post_script || '',
    });
    setCaseModalTab('basic');
    setCaseModalOpen(true);
    // 加载该用例的数据库断言和环境列表
    loadDbAssertions(record.id);
    loadEnvironments();
  }

  async function handleSave() {
    try {
      const values: any = await form.validateFields();
      setSaving(true);
      const payload: TestCaseCreate = {
        title: values.title,
        method: values.method,
        url: values.url,
        headers: values.headers ? JSON.parse(values.headers) : {},
        params: values.params ? JSON.parse(values.params) : {},
        body: values.body ? JSON.parse(values.body) : undefined,
        group_path: values.group_path || undefined,
        project_id: values.project_id || selectedProjectId || undefined,
        markers: [],
        retry_count: values.retry_count ?? 0,
        retry_interval: values.retry_interval ?? 1.0,
        pre_script: values.pre_script || undefined,
        post_script: values.post_script || undefined,
        assertions: [{
          assertion_type: 'status_code', operator: 'eq', expected: '200', priority: 'P0', order: 0,
        }],
      };
      if (editingCase) {
        await testCaseApi.update(editingCase.id, payload);
        message.success('更新成功');
      } else {
        await testCaseApi.create(payload);
        message.success('创建成功');
      }
      setCaseModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  // ---- 移动到项目 ----
  async function confirmMove() {
    if (!moveTargetId) { message.warning('请选择目标项目'); return; }
    setMoving(true);
    try {
      const targetId = moveTargetId === '__none__' ? null : moveTargetId;
      const res = await testCaseApi.batchMove(selectedRowKeys, targetId as string | null);
      message.success(`已移动 ${res.data.moved} 个用例`);
      setMoveModalOpen(false);
      setSelectedRowKeys([]);
      setMoveTargetId('');
      loadData();
    } catch (e: any) { message.error(e.message); }
    finally { setMoving(false); }
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
  function handleDownloadDoc(caseId: string) {
    window.open(`/api/v1/test-cases/${caseId}/doc`, '_blank');
  }

  // ---- 数据库断言 ----
  async function loadDbAssertions(caseId: string) {
    if (!caseId) { setDbAssertions([]); return; }
    setDbAssertionLoading(true);
    try {
      const res = await dbAssertionApi.list(caseId);
      setDbAssertions(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setDbAssertionLoading(false);
    }
  }

  async function loadEnvironments() {
    try {
      const res = await environmentApi.list({ page: 1, page_size: 100 });
      setEnvList(res.data || []);
    } catch (e: any) {
      // 静默失败，不影响主流程
    }
  }

  function openAssertionCreate() {
    setEditingAssertion(null);
    assertionForm.resetFields();
    assertionForm.setFieldsValue({
      operator: 'equals',
      is_active: true,
    });
    setTestResult(null);
    setTestEnvId('');
    setAssertionModalOpen(true);
  }

  function openAssertionEdit(record: any) {
    setEditingAssertion(record);
    const expected = record.expected_result || {};
    assertionForm.setFieldsValue({
      name: record.name,
      sql_template: record.sql_template,
      operator: expected.operator || 'equals',
      field: expected.field,
      value: expected.value,
      is_active: record.is_active,
      description: record.description,
    });
    setTestResult(null);
    setTestEnvId('');
    setAssertionModalOpen(true);
  }

  async function handleAssertionSave() {
    if (!editingCase) { message.warning('请先保存用例'); return; }
    try {
      const values: any = await assertionForm.validateFields();
      setAssertionSaving(true);
      // 预期值：表单收集为字符串，纯数字时转为数值以便 count/greater_than/less_than 正确比对
      let expectedValue: any = values.value;
      if (expectedValue !== undefined && expectedValue !== null && String(expectedValue).trim() !== '') {
        const num = Number(expectedValue);
        if (!isNaN(num)) expectedValue = num;
      } else {
        expectedValue = null;
      }
      const payload = {
        test_case_id: editingCase.id,
        name: values.name,
        sql_template: values.sql_template,
        expected_result: {
          operator: values.operator,
          field: values.field ?? null,
          value: expectedValue,
        },
        is_active: values.is_active ?? true,
        description: values.description,
      };
      if (editingAssertion) {
        await dbAssertionApi.update(editingAssertion.id, payload);
        message.success('断言更新成功');
      } else {
        await dbAssertionApi.create(payload);
        message.success('断言创建成功');
      }
      setAssertionModalOpen(false);
      loadDbAssertions(editingCase.id);
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setAssertionSaving(false);
    }
  }

  async function handleAssertionDelete(id: string) {
    try {
      await dbAssertionApi.delete(id);
      message.success('断言删除成功');
      if (editingCase) loadDbAssertions(editingCase.id);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleAssertionTest() {
    if (!editingAssertion) { message.warning('请先保存断言后再测试'); return; }
    if (!testEnvId) { message.warning('请选择测试环境'); return; }
    setTestingAssertion(true);
    setTestResult(null);
    try {
      const res = await dbAssertionApi.test(editingAssertion.id, testEnvId, {});
      setTestResult(res.data);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setTestingAssertion(false);
    }
  }

  const batchToolbar = selectedRowKeys.length > 0 && (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px', background: '#eff6ff', borderRadius: 6, marginBottom: 12 }}>
      <span style={{ fontWeight: 600, color: '#1e40af' }}>已选中 {selectedRowKeys.length} 个用例</span>
      <Button type="primary" icon={<ThunderboltOutlined />} loading={batchExecuting} onClick={() => handleBatchExecute()}>
        批量执行
      </Button>
      <Button icon={<DragOutlined />} onClick={() => setMoveModalOpen(true)}>移动到项目</Button>
      <Popconfirm title={`确认删除选中的 ${selectedRowKeys.length} 个用例？`} onConfirm={handleBatchDelete}>
        <Button danger icon={<DeleteOutlined />}>批量删除</Button>
      </Popconfirm>
      <Button type="link" onClick={() => setSelectedRowKeys([])}>取消选择</Button>
    </div>
  );

  const columns = [
    {
      title: '排序',
      width: 70,
      render: (_: any, record: TestCase, index: number) => (
        <Space orientation="vertical" size={0}>
          <Button
            size="small"
            type="text"
            icon={<ArrowUpOutlined />}
            disabled={index === 0}
            onClick={() => handleMove(record.id, 'up')}
          />
          <Button
            size="small"
            type="text"
            icon={<ArrowDownOutlined />}
            disabled={index === cases.length - 1}
            onClick={() => handleMove(record.id, 'down')}
          />
        </Space>
      ),
    },
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (m: string) => <Tag color={methodColor[m] || 'default'}>{m}</Tag>,
    },
    { title: '标题', dataIndex: 'title', ellipsis: true, width: 200 },
    { title: 'URL', dataIndex: 'url', ellipsis: true },
    {
      title: '模块',
      dataIndex: 'group_path',
      width: 140,
      render: (v: string) => v ? <Tag icon={<FolderOutlined />}>{v}</Tag> : <span style={{ color: '#9ca3af' }}>-</span>,
    },
    {
      title: '所属项目',
      dataIndex: 'project_id',
      width: 140,
      render: (pid: string) => pid ? projectNameMap.get(pid)?.name || pid : <Tag>未分类</Tag>,
    },
    {
      title: '最近执行',
      width: 100,
      render: (_: any, record: TestCase) => {
        const s = lastResults[record.id];
        return s ? <Badge color={statusBadge[s] || '#d9d9d9'} text={statusLabel[s] || s} /> : '-';
      },
    },
    {
      title: '操作',
      width: 420,
      render: (_: any, record: TestCase) => (
        <Space wrap>
          <Button size="small" type="primary" ghost icon={<PlayCircleOutlined />}
            loading={executingId === record.id}
            onClick={() => handleExecute(record.id)} data-testid="run-btn">
            执行
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} data-testid="edit-btn">编辑</Button>
          <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy(record.id)}>复制</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => openChangeLog(record.id)}>修改历史</Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownloadDoc(record.id)}>下载文档</Button>
          <Popconfirm title="确认删除该用例？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} data-testid="delete-btn">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <span>用例管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>共 {cases.length} 个用例</span>
          </Space>
        }
      >
        {/* 工具栏 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
          <Space wrap>
            <span style={{ fontWeight: 600 }}>项目：</span>
            <Select
              value={selectedProjectId}
              onChange={(v) => { setSelectedProjectId(v); setSelectedGroup(''); }}
              style={{ width: 180 }}
              placeholder="全部项目"
              allowClear
              showSearch
              optionFilterProp="label"
              options={projects.map(p => ({ value: p.id, label: p.name }))}
            />
            <span style={{ fontWeight: 600 }}>模块：</span>
            <Select
              value={selectedGroup || undefined}
              onChange={(v) => setSelectedGroup(v || '')}
              style={{ width: 180 }}
              placeholder="全部模块"
              allowClear
              showSearch
              options={moduleOptions.map(m => ({ value: m, label: m }))}
            />
            <Button type="primary" ghost icon={<PlusOutlined />} onClick={openCreate} data-testid="create-btn">新建用例</Button>
          </Space>
          <Space wrap>
            <Input
              placeholder="搜索 URL"
              allowClear
              style={{ width: 200 }}
              value={urlSearch}
              onChange={(e) => setUrlSearch(e.target.value)}
              prefix={<SearchOutlined />}
              data-testid="search-input"
            />
            <Input
              placeholder="搜索标题"
              allowClear
              style={{ width: 160 }}
              value={titleSearch}
              onChange={(e) => setTitleSearch(e.target.value)}
            />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          </Space>
        </div>

        {/* 批量操作栏 */}
        {batchToolbar}

        {/* 表格 */}
        {cases.length === 0 && !loading ? (
          <Empty description="暂无用例，请新建或导入" style={{ padding: 40 }}>
            <Space>
              <Button type="primary" onClick={openCreate}>新建用例</Button>
            </Space>
          </Empty>
        ) : (
          <Table
            dataSource={cases}
            rowKey="id"
            loading={loading}
            rowSelection={{
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys as string[]),
            }}
            pagination={{ pageSize: 50, showTotal: (t) => `共 ${t} 条` }}
            columns={columns}
            size="middle"
            data-testid="cases-table"
          />
        )}
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editingCase ? '编辑用例' : '新建用例'}
        open={caseModalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setCaseModalOpen(false)}
        width={760}
        destroyOnHidden
        data-testid={editingCase ? 'edit-modal' : 'create-modal'}
      >
        <Tabs
          activeKey={caseModalTab}
          onChange={setCaseModalTab}
          items={[
            {
              key: 'basic',
              label: '基本信息',
              children: (
                <Form form={form} layout="vertical" initialValues={{ method: 'GET' }}>
                  <Form.Item name="title" label="用例标题" rules={[{ required: true, message: '请输入用例标题' }]}>
                    <Input placeholder="如：获取用户列表" />
                  </Form.Item>
                  <Space style={{ width: '100%' }} size="middle">
                    <Form.Item name="method" label="请求方法" rules={[{ required: true }]}>
                      <Select style={{ width: 120 }} options={METHODS.map(m => ({ label: m, value: m }))} />
                    </Form.Item>
                    <Form.Item name="url" label="请求 URL" rules={[{ required: true, message: '请输入 URL' }]}
                      style={{ flex: 1, minWidth: 440 }}>
                      <Input placeholder="http://api.example.com/users" />
                    </Form.Item>
                  </Space>
                  <Form.Item name="group_path" label="模块/分组">
                    <Input placeholder="如：用户管理/认证" />
                  </Form.Item>
                  <Form.Item name="project_id" label="所属项目">
                    <Select
                      allowClear
                      placeholder="选择项目（可选）"
                      options={projects.map(p => ({ label: p.name, value: p.id }))}
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
              ),
            },
            {
              key: 'advanced',
              label: '高级配置',
              children: (
                <Form form={form} layout="vertical">
                  {/* 失败重试 */}
                  <div style={{ marginBottom: 8, fontWeight: 600 }}>失败重试</div>
                  <div style={{ marginBottom: 12, padding: 12, background: '#f9fafb', borderRadius: 6, fontSize: 13, color: '#6b7280' }}>
                    执行失败（断言未通过或出错）时自动重试。重试间隔为秒，设为 0 表示不等待。
                  </div>
                  <Space style={{ width: '100%' }} size="middle">
                    <Form.Item name="retry_count" label="重试次数" style={{ width: 200 }}>
                      <InputNumber min={0} max={10} style={{ width: '100%' }} placeholder="0" />
                    </Form.Item>
                    <Form.Item name="retry_interval" label="重试间隔(秒)" style={{ width: 200 }}>
                      <InputNumber min={0} max={300} step={0.5} style={{ width: '100%' }} placeholder="1.0" />
                    </Form.Item>
                  </Space>

                  {/* 前置脚本 */}
                  <div style={{ marginTop: 16, marginBottom: 8, fontWeight: 600 }}>前置脚本 (Python)</div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    在主请求执行前运行，可访问 <code>variables</code>（变量字典）与 <code>request</code>（请求对象）。
                    修改 <code>variables</code> 中的键值可影响后续请求的变量渲染。禁止使用 os/subprocess/open 等。
                  </div>
                  <Form.Item name="pre_script">
                    <Input.TextArea
                      rows={5}
                      placeholder={'# 示例：动态设置变量\nvariables["trace_id"] = str(len(variables)) + "x"\nprint("前置脚本执行完毕")'}
                      style={{ fontFamily: 'monospace', fontSize: 13 }}
                    />
                  </Form.Item>

                  {/* 后置脚本 */}
                  <div style={{ marginTop: 8, marginBottom: 8, fontWeight: 600 }}>后置脚本 (Python)</div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#f0fdf4', borderRadius: 6, fontSize: 13, color: '#166534' }}>
                    在主请求执行后运行，可访问 <code>response</code>（响应对象：status_code/headers/body/text）与 <code>variables</code>。
                    脚本出错不会中断主流程。
                  </div>
                  <Form.Item name="post_script">
                    <Input.TextArea
                      rows={5}
                      placeholder={'# 示例：校验响应并记录\nif response and response["status_code"] == 200:\n    print("请求成功")'}
                      style={{ fontFamily: 'monospace', fontSize: 13 }}
                    />
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'db-assertion',
              label: '数据库断言',
              children: editingCase ? (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                    <span style={{ color: '#6b7280' }}>
                      为该用例配置数据库断言（执行 SQL 并校验结果，仅支持 SELECT）
                    </span>
                    <Button type="primary" icon={<PlusOutlined />} onClick={openAssertionCreate}>
                      新增断言
                    </Button>
                  </div>
                  <Table
                    dataSource={dbAssertions}
                    rowKey="id"
                    loading={dbAssertionLoading}
                    size="small"
                    pagination={{ pageSize: 5 }}
                    locale={{ emptyText: '暂无数据库断言' }}
                    columns={[
                      { title: '名称', dataIndex: 'name', ellipsis: true, width: 140 },
                      {
                        title: 'SQL 摘要', dataIndex: 'sql_template', ellipsis: true,
                        render: (v: string) => v ? (v.length > 40 ? v.slice(0, 40) + '…' : v) : '-',
                      },
                      {
                        title: '操作符', width: 110,
                        render: (_: any, r: any) => r.expected_result?.operator || '-',
                      },
                      {
                        title: '启用', dataIndex: 'is_active', width: 70,
                        render: (v: boolean) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag>,
                      },
                      {
                        title: '操作', width: 130,
                        render: (_: any, record: any) => (
                          <Space>
                            <Button size="small" icon={<EditOutlined />} onClick={() => openAssertionEdit(record)}>
                              编辑
                            </Button>
                            <Popconfirm title="确认删除该断言？" onConfirm={() => handleAssertionDelete(record.id)}>
                              <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                            </Popconfirm>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </div>
              ) : (
                <Empty description="新建用例保存后才能配置数据库断言" style={{ padding: 40 }} />
              ),
            },
          ]}
        />
      </Modal>

      {/* 数据库断言编辑 Modal */}
      <Modal
        title={editingAssertion ? '编辑数据库断言' : '新增数据库断言'}
        open={assertionModalOpen}
        onOk={handleAssertionSave}
        confirmLoading={assertionSaving}
        onCancel={() => setAssertionModalOpen(false)}
        width={680}
        destroyOnHidden
      >
        <Form form={assertionForm} layout="vertical">
          <Form.Item name="name" label="断言名称" rules={[{ required: true, message: '请输入断言名称' }]}>
            <Input placeholder="如：校验用户已存在" />
          </Form.Item>
          <Form.Item
            name="sql_template"
            label="SQL 模板（仅支持 SELECT，可用 ${var} 占位）"
            rules={[{ required: true, message: '请输入 SQL 模板' }]}
          >
            <Input.TextArea
              rows={4}
              placeholder="SELECT id, name FROM users WHERE name = '${username}'"
            />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle" align="start">
            <Form.Item
              name="operator"
              label="操作符"
              rules={[{ required: true, message: '请选择操作符' }]}
              style={{ width: 200 }}
            >
              <Select options={DB_OPERATORS} />
            </Form.Item>
            <Form.Item name="field" label="字段名（count 可留空）" style={{ flex: 1, minWidth: 180 }}>
              <Input placeholder="如 id（取首行该字段值）" />
            </Form.Item>
          </Space>
          <Form.Item name="value" label="预期值（count/equals 比对值）">
            <Input placeholder="如 1（与实际值比对）" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="断言说明（可选）" />
          </Form.Item>

          {/* 测试区域 */}
          {editingAssertion && (
            <div style={{ marginTop: 8, padding: 12, background: '#fafafa', borderRadius: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>测试断言</div>
              <Space style={{ width: '100%' }} size="middle">
                <Select
                  value={testEnvId || undefined}
                  onChange={setTestEnvId}
                  style={{ width: 240 }}
                  placeholder="选择测试环境"
                  showSearch
                  optionFilterProp="label"
                  options={envList.map(e => ({ value: e.id, label: e.name }))}
                />
                <Button
                  icon={<ExperimentOutlined />}
                  loading={testingAssertion}
                  onClick={handleAssertionTest}
                >
                  执行测试
                </Button>
              </Space>
              {testResult && (
                <div style={{ marginTop: 12 }}>
                  <Alert
                    type={testResult.passed ? 'success' : 'error'}
                    showIcon
                    title={testResult.passed ? '断言通过' : '断言未通过'}
                    description={
                      <div style={{ fontSize: 13 }}>
                        <div><span style={{ color: '#6b7280' }}>SQL：</span><code>{testResult.sql}</code></div>
                        <div>
                          <span style={{ color: '#6b7280' }}>实际值：</span>
                          <span>{testResult.actual === null ? 'null' : String(testResult.actual)}</span>
                        </div>
                        <div>
                          <span style={{ color: '#6b7280' }}>预期值：</span>
                          <span>{JSON.stringify(testResult.expected)}</span>
                        </div>
                      </div>
                    }
                  />
                </div>
              )}
            </div>
          )}
        </Form>
      </Modal>

      {/* 移动到项目 Modal */}
      <Modal
        title={`移动 ${selectedRowKeys.length} 个用例到项目`}
        open={moveModalOpen}
        onOk={confirmMove}
        confirmLoading={moving}
        onCancel={() => setMoveModalOpen(false)}
        destroyOnHidden
      >
        <div style={{ marginBottom: 12, color: '#6b7280' }}>选择目标项目，选中的用例将移动到该项目下。</div>
        <Select
          value={moveTargetId || undefined}
          onChange={setMoveTargetId}
          style={{ width: '100%' }}
          placeholder="选择目标项目"
          showSearch
          optionFilterProp="label"
          options={[
            { value: '__none__', label: '移出项目（变为未分类）' },
            ...projects.map(p => ({ value: p.id, label: p.name })),
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
              {[
                { label: '总计', value: batchResults.total, color: '#374151' },
                { label: '通过', value: batchResults.passed, color: '#52c41a' },
                { label: '失败', value: batchResults.failed, color: '#ff4d4f' },
                { label: '错误', value: batchResults.error, color: '#faad14' },
              ].map(item => (
                <div key={item.label}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: item.color }}>{item.value}</div>
                  <div style={{ color: '#6b7280' }}>{item.label}</div>
                </div>
              ))}
              <div style={{ flex: 1 }}>
                <Progress
                  percent={batchResults.total > 0 ? Math.round((batchResults.passed / batchResults.total) * 100) : 0}
                  strokeColor="#52c41a"
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
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (s: string) => <Badge color={statusBadge[s] || '#d9d9d9'} text={statusLabel[s] || s} />,
                },
                { title: '标题', dataIndex: 'title', ellipsis: true },
                {
                  title: '状态码', dataIndex: 'status_code', width: 80,
                  render: (c: number) => c || '-',
                },
                {
                  title: '耗时(s)', dataIndex: 'duration', width: 80,
                  render: (d: number) => d ? d.toFixed(3) : '-',
                },
                {
                  title: '错误', dataIndex: 'error', ellipsis: true,
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
    </div>
  );
}
