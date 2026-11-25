import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tree,
  Typography,
  message,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiCaseRecordApi, type ApiCaseRecord } from '../services/api';
import {
  buildGroupSelectOptions,
  buildGroupTree,
  groupItemsByPath,
  normalizeGroupPath,
} from '../utils/apiModules';
import { parseJsonText } from '../utils/json';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const METHOD_COLOR: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'purple',
  DELETE: 'red',
};

const CASE_TYPE_LABEL: Record<string, string> = {
  normal: '正常',
  exception: '异常',
  boundary: '边界',
  permission: '权限',
};

const CASE_TYPE_COLOR: Record<string, string> = {
  normal: 'green',
  exception: 'volcano',
  boundary: 'gold',
  permission: 'purple',
};

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  active: '已确认',
  archived: '已归档',
};

const STATUS_OPTIONS = Object.entries(STATUS_LABEL).map(([value, label]) => ({
  value,
  label,
}));

const PRIORITY_OPTIONS = ['P0', 'P1', 'P2', 'P3'].map((value) => ({
  value,
  label: value,
}));

const CASE_TYPE_OPTIONS = Object.entries(CASE_TYPE_LABEL).map(([value, label]) => ({
  value,
  label,
}));

const METHOD_OPTIONS = Object.keys(METHOD_COLOR).map((value) => ({
  value,
  label: value,
}));

/** 列表展示模式：按模块分组显示 / 平铺列表 */
type ViewMode = 'grouped' | 'flat';

/** 模块树节点被选中时，用这个键表示「未分组」 */
const UNGROUPED_KEY = '__ungrouped__';

/**
 * 编辑表单里 JSON 字段先以文本编辑，提交时再解析。
 * 这样即使 JSON 写错也不会丢用户输入，能给出明确报错。
 */
type CaseFormValues = {
  title: string;
  method: string;
  url: string;
  case_type: string;
  priority: string;
  status: string;
  interface_name?: string | null;
  group_path?: string | null;
  description?: string | null;
  headersText: string;
  paramsText: string;
  bodyText: string;
  assertionsText: string;
};

function toJsonText(value: unknown, emptyFallback = ''): string {
  if (value === undefined || value === null) return emptyFallback;
  return JSON.stringify(value, null, 2);
}

function recordToForm(record: ApiCaseRecord): CaseFormValues {
  return {
    title: record.title,
    method: record.method,
    url: record.url,
    case_type: record.case_type,
    priority: record.priority,
    status: record.status,
    interface_name: record.interface_name || '',
    group_path: record.group_path || '',
    description: record.description || '',
    headersText: toJsonText(record.headers, '{}'),
    paramsText: toJsonText(record.params, '{}'),
    bodyText: toJsonText(record.body),
    assertionsText: toJsonText(record.assertions, '[]'),
  };
}

export default function ApiCaseManagementPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ApiCaseRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [method, setMethod] = useState<string | undefined>();
  const [caseType, setCaseType] = useState<string | undefined>();
  const [priority, setPriority] = useState<string | undefined>();
  const [stats, setStats] = useState<Record<string, number>>({});
  const [detail, setDetail] = useState<ApiCaseRecord | null>(null);

  // 模块视图
  const [viewMode, setViewMode] = useState<ViewMode>('grouped');
  const [groupFilter, setGroupFilter] = useState<string | undefined>();
  const [groupPaths, setGroupPaths] = useState<string[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  // 编辑表单
  const [editing, setEditing] = useState<ApiCaseRecord | null>(null);
  const [form] = Form.useForm<CaseFormValues>();
  const [saving, setSaving] = useState(false);

  // 点击用例标题即打开编辑，这是本页的主要操作路径；
  // 「详情」保留为收起的次级入口。
  const openEdit = useCallback(
    (record: ApiCaseRecord) => {
      setEditing(record);
      form.setFieldsValue(recordToForm(record));
    },
    [form]
  );

  const closeEdit = useCallback(() => {
    setEditing(null);
    form.resetFields();
  }, [form]);

  const loadData = useCallback(
    async (p = page, ps = pageSize) => {
      setLoading(true);
      try {
        // 按模块视图时一次性拉取该模块下的全部用例，才能在页面上分组；
        // 平铺视图沿用分页。
        const res = await apiCaseRecordApi.list({
          page: viewMode === 'grouped' ? 1 : p,
          page_size: viewMode === 'grouped' ? 200 : ps,
          keyword: keyword || undefined,
          group_path: groupFilter,
          method,
          case_type: caseType,
          priority,
        });
        setData(res.data || []);
        setTotal(res.total || 0);
        setSelectedRowKeys([]);
      } catch (e: any) {
        message.error(e.message);
      } finally {
        setLoading(false);
      }
    },
    [keyword, method, caseType, page, pageSize, priority, groupFilter, viewMode]
  );

  const loadStats = useCallback(async () => {
    try {
      const res = await apiCaseRecordApi.stats();
      setStats(res.data || {});
    } catch {
      // 统计失败不阻断列表
    }
  }, []);

  const loadGroups = useCallback(async () => {
    try {
      const res = await apiCaseRecordApi.groups();
      setGroupPaths((res.data || []).map((item) => item.path));
    } catch {
      // 模块列表失败不阻断列表
    }
  }, []);

  useEffect(() => {
    loadData(1, pageSize);
    loadStats();
    loadGroups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [method, caseType, priority, groupFilter, viewMode]);

  async function handleDelete(id: string) {
    try {
      await apiCaseRecordApi.remove(id);
      message.success('用例已删除');
      await Promise.all([loadData(), loadStats(), loadGroups()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleBatchDelete() {
    if (selectedRowKeys.length === 0) return;
    try {
      const res = await apiCaseRecordApi.batchDelete(selectedRowKeys.map(String));
      message.success(`已删除 ${res.data?.deleted ?? 0} 条用例`);
      await Promise.all([loadData(), loadStats(), loadGroups()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleBatchMove(targetGroup: string | null) {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要移动的用例');
      return;
    }
    try {
      const res = await apiCaseRecordApi.batchMove(
        selectedRowKeys.map(String),
        targetGroup
      );
      message.success(
        `已把 ${res.data?.moved ?? 0} 条用例移动到「${targetGroup || '未分组'}」`
      );
      await Promise.all([loadData(), loadGroups()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleSaveEdit() {
    if (!editing) return;
    let values: CaseFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    let headers: unknown;
    let params: unknown;
    let body: unknown;
    let assertions: unknown;
    try {
      headers = parseJsonText(values.headersText, '请求头', {
        expectedType: 'object',
      });
      params = parseJsonText(values.paramsText, '查询参数', {
        expectedType: 'object',
      });
      body = parseJsonText(values.bodyText, '请求体');
      assertions = parseJsonText(values.assertionsText, '断言', {
        expectedType: 'array',
      });
    } catch (e: any) {
      message.error(e.message);
      return;
    }

    setSaving(true);
    try {
      await apiCaseRecordApi.update(editing.id, {
        title: values.title,
        method: values.method,
        url: values.url,
        case_type: values.case_type,
        priority: values.priority,
        status: values.status,
        interface_name: values.interface_name || null,
        group_path: normalizeGroupPath(values.group_path) || null,
        description: values.description || null,
        headers: (headers as Record<string, any>) || {},
        params: (params as Record<string, any>) || {},
        body: body ?? null,
        assertions: (assertions as any[]) || [],
      });
      message.success('用例已保存');
      closeEdit();
      // 编辑可能改了模块归属，模块列表也要刷新
      await Promise.all([loadData(), loadStats(), loadGroups()]);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleExport() {
    const url = apiCaseRecordApi.exportUrl({
      keyword: keyword || undefined,
      group_path: groupFilter,
      method,
      case_type: caseType,
      priority,
    });
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`导出失败（HTTP ${response.status}）`);
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `接口用例-${new Date().toISOString().slice(0, 10)}.xlsx`;
      link.click();
      URL.revokeObjectURL(link.href);
      message.success(`已按当前筛选条件导出 ${total} 条用例`);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 模块树：来自后端模块清单 + 当前列表里出现的路径，保证两边都不丢
  const moduleTree = useMemo(
    () =>
      buildGroupTree(
        data,
        [...groupPaths, ...data.map((item) => item.group_path || '')],
        { includeUngrouped: true }
      ),
    [data, groupPaths]
  );

  const moduleTreeData = useMemo<DataNode[]>(() => {
    function toNode(node: (typeof moduleTree)[number]): DataNode {
      return {
        key: node.path === '' ? UNGROUPED_KEY : node.path,
        title: (
          <Space size={4}>
            <FolderOpenOutlined
              style={{ color: node.path ? '#d97706' : '#9ca3af' }}
            />
            <span>{node.name}</span>
            <Tag style={{ marginInlineEnd: 0 }}>{node.totalCount}</Tag>
          </Space>
        ),
        children: node.children.map(toNode),
      };
    }
    return moduleTree.map(toNode);
  }, [moduleTree]);

  const groupSelectOptions = useMemo(
    () => buildGroupSelectOptions(groupPaths, { includeEmpty: true }),
    [groupPaths]
  );

  const columns = useMemo(
    () => [
      {
        title: '用例标题',
        dataIndex: 'title',
        ellipsis: true,
        render: (value: string, record: ApiCaseRecord) => (
          // 点击用例直接进入编辑
          <Space size={4}>
            <a onClick={() => openEdit(record)} title="点击编辑该用例">
              {value}
            </a>
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              aria-label="编辑用例"
              onClick={() => openEdit(record)}
            />
          </Space>
        ),
      },
      {
        title: '场景',
        dataIndex: 'case_type',
        width: 90,
        render: (value: string) => (
          <Tag color={CASE_TYPE_COLOR[value] || 'default'}>
            {CASE_TYPE_LABEL[value] || value}
          </Tag>
        ),
      },
      {
        title: '方法',
        dataIndex: 'method',
        width: 80,
        render: (value: string) => (
          <Tag color={METHOD_COLOR[value] || 'default'}>{value}</Tag>
        ),
      },
      { title: 'URL', dataIndex: 'url', ellipsis: true, width: 240 },
      {
        title: '优先级',
        dataIndex: 'priority',
        width: 80,
        render: (value: string) => <Tag>{value}</Tag>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 90,
        render: (value: string) => (
          <Tag color={value === 'active' ? 'success' : 'default'}>
            {STATUS_LABEL[value] || value}
          </Tag>
        ),
      },
      // 分组视图里已经在模块标题上体现了模块，不再重复一列
      ...(viewMode === 'flat'
        ? [
            {
              title: '模块',
              dataIndex: 'group_path',
              width: 160,
              ellipsis: true,
              render: (value: string | null) => value || '未分组',
            },
          ]
        : []),
      {
        title: '关联接口',
        dataIndex: 'interface_name',
        width: 150,
        ellipsis: true,
        render: (value: string | null) => value || '-',
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        width: 170,
        render: (value: string) => (value ? new Date(value).toLocaleString() : '-'),
      },
      {
        title: '操作',
        width: 170,
        render: (_: unknown, record: ApiCaseRecord) => (
          <Space size={0}>
            <Button type="link" size="small" onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Button type="link" size="small" onClick={() => setDetail(record)}>
              详情
            </Button>
            <Popconfirm
              title="确认删除该用例？"
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    // handleDelete 只依赖 setState 与 message，无需进入依赖数组
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [viewMode, openEdit]
  );

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  };

  // 模块树当前选中项：undefined 表示「全部模块」，'' 表示未分组
  const selectedTreeKeys = useMemo<React.Key[]>(() => {
    if (groupFilter === undefined) return [];
    return [normalizeGroupPath(groupFilter) === '' ? UNGROUPED_KEY : groupFilter];
  }, [groupFilter]);

  const groupedBuckets = useMemo(() => groupItemsByPath(data), [data]);

  return (
    <div>
      <Card
        title={
          <Space>
            <UnorderedListOutlined />
            <span>用例管理</span>
            <Tag color="blue">接口用例库</Tag>
          </Space>
        }
        extra={
          <Space wrap>
            <Input.Search
              placeholder="搜索用例标题"
              allowClear
              style={{ width: 180 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={() => loadData(1, pageSize)}
            />
            <Select
              allowClear
              placeholder="模块"
              style={{ width: 160 }}
              value={groupFilter}
              onChange={(value) => {
                setGroupFilter(value);
                setPage(1);
              }}
              options={groupSelectOptions.map((option) => ({
                value: option.value,
                label: option.display,
              }))}
            />
            <Select
              allowClear
              placeholder="方法"
              style={{ width: 100 }}
              value={method}
              onChange={(value) => {
                setMethod(value);
                setPage(1);
              }}
              options={METHOD_OPTIONS}
            />
            <Select
              allowClear
              placeholder="场景"
              style={{ width: 100 }}
              value={caseType}
              onChange={(value) => {
                setCaseType(value);
                setPage(1);
              }}
              options={CASE_TYPE_OPTIONS}
            />
            <Select
              allowClear
              placeholder="优先级"
              style={{ width: 100 }}
              value={priority}
              onChange={(value) => {
                setPriority(value);
                setPage(1);
              }}
              options={PRIORITY_OPTIONS}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleExport}>
              导出 Excel
            </Button>
            <Button type="primary" onClick={() => navigate('/api-case-generation')}>
              去生成用例
            </Button>
          </Space>
        }
      >
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[
            { label: '用例总数', value: stats.total || 0 },
            { label: '模块数', value: stats.group_count || 0 },
            { label: '正常场景', value: stats.normal || 0 },
            { label: '异常场景', value: stats.exception || 0 },
            { label: '边界场景', value: stats.boundary || 0 },
            { label: 'P0 用例', value: stats.p0 || 0 },
          ].map((item) => (
            <Col key={item.label} xs={12} sm={8} md={4}>
              <Card size="small">
                <Statistic title={item.label} value={item.value} />
              </Card>
            </Col>
          ))}
        </Row>

        <Space style={{ marginBottom: 12 }} wrap>
          <Segmented<ViewMode>
            value={viewMode}
            onChange={(value) => {
              setViewMode(value);
              setPage(1);
            }}
            options={[
              { label: '按模块分组', value: 'grouped' },
              { label: '平铺列表', value: 'flat' },
            ]}
          />
          {selectedRowKeys.length > 0 && (
            <>
              <Tag color="blue">已选 {selectedRowKeys.length} 条</Tag>
              <Select
                placeholder="批量移动到模块"
                style={{ width: 180 }}
                value={null}
                onChange={(value) => handleBatchMove(value ?? null)}
                options={groupSelectOptions.map((option) => ({
                  value: option.value,
                  label: option.display,
                }))}
              />
              <Popconfirm
                title={`确认删除选中的 ${selectedRowKeys.length} 条用例？`}
                onConfirm={handleBatchDelete}
              >
                <Button danger size="small" icon={<DeleteOutlined />}>
                  批量删除
                </Button>
              </Popconfirm>
              <Button size="small" onClick={() => setSelectedRowKeys([])}>
                取消选择
              </Button>
            </>
          )}
        </Space>

        {data.length === 0 && !loading ? (
          <Empty
            description="还没有接口用例，点击右上角「去生成用例」按接口或模块生成"
            style={{ padding: 40 }}
          >
            <Button type="primary" onClick={() => navigate('/api-case-generation')}>
              去生成用例
            </Button>
          </Empty>
        ) : viewMode === 'grouped' ? (
          <Row gutter={16}>
            <Col xs={24} lg={7} xl={6} style={{ marginBottom: 12 }}>
              <Card size="small" title="模块目录" styles={{ body: { padding: 8 } }}>
                <Tree
                  treeData={moduleTreeData}
                  defaultExpandAll
                  blockNode
                  selectedKeys={selectedTreeKeys}
                  onSelect={(keys) => {
                    const key = String(keys[0] ?? '');
                    if (!key) {
                      setGroupFilter(undefined);
                    } else if (key === UNGROUPED_KEY) {
                      setGroupFilter('');
                    } else {
                      setGroupFilter(key);
                    }
                    setPage(1);
                  }}
                />
              </Card>
            </Col>
            <Col xs={24} lg={17} xl={18}>
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                {groupedBuckets.map((bucket) => (
                  <Card
                    key={bucket.path || '__ungrouped__'}
                    size="small"
                    title={
                      <Space>
                        <FolderOpenOutlined
                          style={{ color: bucket.path ? '#d97706' : '#9ca3af' }}
                        />
                        <span>{bucket.path || '未分组'}</span>
                        <Tag>{bucket.items.length}</Tag>
                      </Space>
                    }
                  >
                    <Table
                      rowKey="id"
                      size="small"
                      loading={loading}
                      dataSource={bucket.items}
                      columns={columns}
                      tableLayout="fixed"
                      scroll={{ x: 1100 }}
                      rowSelection={rowSelection}
                      pagination={false}
                    />
                  </Card>
                ))}
              </Space>
            </Col>
          </Row>
        ) : (
          <Table
            rowKey="id"
            loading={loading}
            dataSource={data}
            columns={columns}
            tableLayout="fixed"
            scroll={{ x: 1300 }}
            rowSelection={rowSelection}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              onChange: (p, ps) => {
                setPage(p);
                setPageSize(ps);
                loadData(p, ps);
              },
            }}
          />
        )}
      </Card>

      <Modal
        title={`编辑用例${editing ? `：${editing.title}` : ''}`}
        open={Boolean(editing)}
        onCancel={closeEdit}
        onOk={handleSaveEdit}
        confirmLoading={saving}
        width="min(900px, 94vw)"
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="修改后点击「保存」生效；请求头/参数需为 JSON 对象，断言需为 JSON 数组"
        />
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            label="用例标题"
            name="title"
            rules={[{ required: true, message: '请输入用例标题' }]}
          >
            <Input placeholder="例如：参数 tableName 缺失时返回校验错误" />
          </Form.Item>

          <Row gutter={12}>
            <Col xs={24} sm={6}>
              <Form.Item label="方法" name="method" rules={[{ required: true }]}>
                <Select options={METHOD_OPTIONS} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={18}>
              <Form.Item
                label="接口地址"
                name="url"
                rules={[{ required: true, message: '请输入接口地址' }]}
              >
                <Input placeholder="/api/v1/xxx" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={12}>
            <Col xs={24} sm={8}>
              <Form.Item label="场景" name="case_type" rules={[{ required: true }]}>
                <Select options={CASE_TYPE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={5}>
              <Form.Item label="优先级" name="priority" rules={[{ required: true }]}>
                <Select options={PRIORITY_OPTIONS} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={5}>
              <Form.Item label="状态" name="status" rules={[{ required: true }]}>
                <Select options={STATUS_OPTIONS} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={6}>
              <Form.Item label="关联接口" name="interface_name">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            label="所属模块（分组）"
            name="group_path"
            extra="用 / 表示层级，例如 磐石关务/回执；留空表示未分组。可直接输入新模块路径"
          >
            {/* 用 AutoComplete 而不是 Select：既要能从已有模块里选，也要能直接录入新路径 */}
            <AutoComplete
              allowClear
              placeholder="选择模块，或输入新路径"
              options={groupSelectOptions.map((option) => ({
                value: option.value,
                label: option.display,
              }))}
              filterOption={(input, option) =>
                String(option?.value || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Form.Item>

          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item label="请求头 JSON" name="headersText">
                <TextArea
                  rows={4}
                  style={{ fontFamily: 'Consolas, "Courier New", monospace' }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="查询参数 JSON" name="paramsText">
                <TextArea
                  rows={4}
                  style={{ fontFamily: 'Consolas, "Courier New", monospace' }}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="请求体 JSON" name="bodyText">
            <TextArea
              rows={5}
              placeholder='{"username": "test"}'
              style={{ fontFamily: 'Consolas, "Courier New", monospace' }}
            />
          </Form.Item>

          <Form.Item label="断言 JSON" name="assertionsText">
            <TextArea
              rows={4}
              placeholder='[{"type": "status_code", "expected": 200}]'
              style={{ fontFamily: 'Consolas, "Courier New", monospace' }}
            />
          </Form.Item>

          <Form.Item label="描述" name="description">
            <TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={detail?.title || '用例详情'}
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        width="min(760px, 92vw)"
        extra={
          detail ? (
            <Button
              type="primary"
              onClick={() => {
                const record = detail;
                setDetail(null);
                openEdit(record);
              }}
            >
              编辑
            </Button>
          ) : null
        }
      >
        {detail && (
          <>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="场景">
                <Tag color={CASE_TYPE_COLOR[detail.case_type]}>
                  {CASE_TYPE_LABEL[detail.case_type] || detail.case_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag>{detail.priority}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="方法">
                <Tag color={METHOD_COLOR[detail.method] || 'default'}>
                  {detail.method}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {STATUS_LABEL[detail.status] || detail.status}
              </Descriptions.Item>
              <Descriptions.Item label="URL" span={2}>
                <Text code>{detail.url}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="关联接口" span={2}>
                {detail.interface_name || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="模块" span={2}>
                {detail.group_path || '未分组'}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title="请求头" style={{ marginTop: 12 }}>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(detail.headers || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="查询参数" style={{ marginTop: 12 }}>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(detail.params || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="请求体" style={{ marginTop: 12 }}>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(detail.body ?? null, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="断言" style={{ marginTop: 12 }}>
              <Paragraph style={{ marginBottom: 0 }}>
                <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(detail.assertions || [], null, 2)}
                </pre>
              </Paragraph>
            </Card>
          </>
        )}
      </Drawer>
    </div>
  );
}
