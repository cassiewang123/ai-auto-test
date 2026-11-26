import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ExperimentOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { functionalTestCaseApi } from '../services/api';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type FunctionalCase = {
  id: string;
  title: string;
  module?: string | null;
  category: string;
  priority: string;
  preconditions?: string | null;
  steps: string[];
  expected?: string | null;
  trace_source?: string | null;
  status: string;
  source: string;
  requirement_id?: string | null;
  last_result?: string | null;
  last_executed_at?: string | null;
  created_at?: string;
};

const CATEGORY_COLOR: Record<string, string> = {
  功能: 'blue',
  异常: 'volcano',
  边界: 'gold',
  权限: 'purple',
  安全: 'red',
};

const PRIORITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'orange',
  P2: 'blue',
  P3: 'default',
};

const STATUS_OPTIONS = [
  { label: '草稿', value: 'draft' },
  { label: '可执行', value: 'active' },
  { label: '已废弃', value: 'deprecated' },
];

const RESULT_OPTIONS = [
  { label: '通过', value: 'passed' },
  { label: '失败', value: 'failed' },
  { label: '阻塞', value: 'blocked' },
  { label: '跳过', value: 'skipped' },
];

const RESULT_COLOR: Record<string, string> = {
  passed: 'success',
  failed: 'error',
  blocked: 'warning',
  skipped: 'default',
};

const RESULT_LABEL: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  blocked: '阻塞',
  skipped: '跳过',
};

export default function FunctionalTestCasesPage() {
  const [data, setData] = useState<FunctionalCase[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [priority, setPriority] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [stats, setStats] = useState<Record<string, number>>({});

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<FunctionalCase | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const [detailOpen, setDetailOpen] = useState(false);
  const [activeCase, setActiveCase] = useState<FunctionalCase | null>(null);
  const [executions, setExecutions] = useState<any[]>([]);
  const [executing, setExecuting] = useState(false);
  const [execForm] = Form.useForm();

  // 批量删除：勾选集合与提交中状态
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);

  const loadData = useCallback(
    async (p = page, ps = pageSize) => {
      setLoading(true);
      try {
        const res = await functionalTestCaseApi.list({
          page: p,
          page_size: ps,
          keyword: keyword || undefined,
          priority,
          status,
        });
        setData(res.data || []);
        setTotal(res.total || 0);
      } catch (e: any) {
        message.error(e.message);
      } finally {
        setLoading(false);
      }
    },
    [keyword, page, pageSize, priority, status]
  );

  const loadStats = useCallback(async () => {
    try {
      const res = await functionalTestCaseApi.stats();
      setStats(res.data || {});
    } catch {
      // 统计失败不阻断列表
    }
  }, []);

  async function handleBatchDelete() {
    if (selectedRowKeys.length === 0) return;
    setBatchDeleting(true);
    try {
      const res = await functionalTestCaseApi.batchRemove(
        selectedRowKeys.map(String)
      );
      const deleted = res.data?.deleted ?? 0;
      const missing = res.data?.missing ?? 0;
      message.success(
        `已删除 ${deleted} 条用例${missing > 0 ? `（${missing} 条已不存在）` : ''}`
      );
      setSelectedRowKeys([]);
      // 删除后当前页可能被删空，回到第一页重新加载更稳妥
      setPage(1);
      await Promise.all([loadData(1, pageSize), loadStats()]);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBatchDeleting(false);
    }
  }

  useEffect(() => {
    loadData(1, pageSize);
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priority, status]);

  async function handleExport() {
    // 直接下载需要携带 JWT，用 fetch 拉取 blob 后触发浏览器下载
    const url = functionalTestCaseApi.exportUrl({
      keyword: keyword || undefined,
      priority,
      status,
    });
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error(`导出失败（HTTP ${response.status}）`);
      }
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `功能测试用例-${new Date()
        .toISOString()
        .slice(0, 10)}.xlsx`;
      link.click();
      URL.revokeObjectURL(link.href);
      message.success(`已导出 ${data.length} 条用例（按当前筛选条件）`);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      priority: 'P1',
      status: 'active',
      category: '功能',
      steps: [''],
    });
    setModalOpen(true);
  }

  function openEdit(record: FunctionalCase) {
    setEditing(record);
    form.setFieldsValue({
      title: record.title,
      module: record.module,
      category: record.category,
      priority: record.priority,
      status: record.status,
      preconditions: record.preconditions,
      steps: record.steps?.length ? record.steps : [''],
      expected: record.expected,
      trace_source: record.trace_source,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    const values = await form.validateFields();
    const payload = {
      ...values,
      steps: (values.steps || []).filter((step: string) => step?.trim()),
    };
    setSubmitting(true);
    try {
      if (editing) {
        await functionalTestCaseApi.update(editing.id, payload);
        message.success('用例已更新');
      } else {
        await functionalTestCaseApi.create(payload);
        message.success('用例已创建');
      }
      setModalOpen(false);
      await Promise.all([loadData(), loadStats()]);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await functionalTestCaseApi.remove(id);
      message.success('用例已删除');
      await Promise.all([loadData(), loadStats()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function openDetail(record: FunctionalCase) {
    setActiveCase(record);
    setDetailOpen(true);
    execForm.resetFields();
    execForm.setFieldsValue({ result: 'passed' });
    try {
      const res = await functionalTestCaseApi.listExecutions(record.id);
      setExecutions(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleAddExecution() {
    if (!activeCase) return;
    const values = await execForm.validateFields();
    setExecuting(true);
    try {
      await functionalTestCaseApi.addExecution(activeCase.id, values);
      message.success('执行结果已记录');
      execForm.resetFields();
      execForm.setFieldsValue({ result: 'passed' });
      const [history, detail] = await Promise.all([
        functionalTestCaseApi.listExecutions(activeCase.id),
        functionalTestCaseApi.get(activeCase.id),
      ]);
      setExecutions(history.data || []);
      setActiveCase(detail.data);
      await loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setExecuting(false);
    }
  }

  const columns = [
    {
      title: '用例标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (value: string, record: FunctionalCase) => (
        <a onClick={() => openDetail(record)}>{value}</a>
      ),
    },
    {
      title: '模块',
      dataIndex: 'module',
      width: 130,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 90,
      render: (value: string) => (
        <Tag color={CATEGORY_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (value: string) => (
        <Tag color={PRIORITY_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '步骤',
      dataIndex: 'steps',
      width: 70,
      render: (value: string[]) => value?.length || 0,
    },
    {
      title: '最近执行',
      dataIndex: 'last_result',
      width: 110,
      render: (value: string | null) =>
        value ? (
          <Tag color={RESULT_COLOR[value]}>{RESULT_LABEL[value] || value}</Tag>
        ) : (
          <Text type="secondary">未执行</Text>
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={value === 'active' ? 'success' : 'default'}>
          {STATUS_OPTIONS.find((item) => item.value === value)?.label || value}
        </Tag>
      ),
    },
    {
      title: '操作',
      width: 200,
      render: (_: unknown, record: FunctionalCase) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openDetail(record)}>
            详情/执行
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
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
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <ExperimentOutlined />
            <span>功能测试用例</span>
            <Tag color="blue">人工执行 · 区别于 API 自动化用例</Tag>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索用例标题"
              allowClear
              style={{ width: 200 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={() => loadData(1, pageSize)}
            />
            <Select
              placeholder="优先级"
              allowClear
              style={{ width: 110 }}
              value={priority}
              onChange={(value) => {
                setPriority(value);
                setPage(1);
              }}
              options={['P0', 'P1', 'P2', 'P3'].map((v) => ({ label: v, value: v }))}
            />
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 110 }}
              value={status}
              onChange={(value) => {
                setStatus(value);
                setPage(1);
              }}
              options={STATUS_OPTIONS}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleExport}>
              导出 Excel
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建用例
            </Button>
          </Space>
        }
      >
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[
            { label: '用例总数', value: stats.total || 0 },
            { label: '可执行', value: stats.active || 0 },
            { label: '草稿', value: stats.draft || 0 },
            { label: 'P0 用例', value: stats.p0 || 0 },
            { label: '覆盖需求', value: stats.covered_requirements || 0 },
          ].map((item) => (
            <Col key={item.label} xs={12} sm={8} md={4}>
              <Card size="small">
                <Statistic title={item.label} value={item.value} />
              </Card>
            </Col>
          ))}
        </Row>

        {stats.total > 0 && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="功能测试用例不绑定接口请求，由测试人员在用例详情中登记执行结果"
          />
        )}

        {selectedRowKeys.length > 0 && (
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag color="blue">已选 {selectedRowKeys.length} 条</Tag>
            <Popconfirm
              title={`确认删除选中的 ${selectedRowKeys.length} 条用例？`}
              description="删除后不可恢复，用例的执行记录也会一并删除。"
              okText="确认删除"
              okButtonProps={{ danger: true }}
              onConfirm={handleBatchDelete}
            >
              <Button danger icon={<DeleteOutlined />} loading={batchDeleting}>
                批量删除（{selectedRowKeys.length}）
              </Button>
            </Popconfirm>
            <Button onClick={() => setSelectedRowKeys([])}>取消选择</Button>
          </Space>
        )}

        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          columns={columns}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            // 翻页后保留已勾选，避免跨页选择被清空
            preserveSelectedRowKeys: true,
          }}
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
      </Card>

      <Modal
        title={editing ? '编辑功能测试用例' : '新建功能测试用例'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        width={760}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="用例标题"
            rules={[{ required: true, message: '请输入用例标题' }]}
          >
            <Input placeholder="例如：已审批启用用户使用正确用户名密码登录成功" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="module" label="所属模块">
                <Input placeholder="例如：登录与认证" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="category" label="分类">
                <Select
                  options={['功能', '异常', '边界', '权限', '安全'].map((v) => ({
                    label: v,
                    value: v,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="priority" label="优先级">
                <Select
                  options={['P0', 'P1', 'P2', 'P3'].map((v) => ({
                    label: v,
                    value: v,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="status" label="状态">
                <Select options={STATUS_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="preconditions" label="前置条件">
            <TextArea rows={2} placeholder="执行该用例前需要准备的数据与环境" />
          </Form.Item>
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                <Form.Item label="操作步骤" required>
                  {fields.map((field, index) => (
                    <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }}>
                      <Text style={{ width: 24 }}>{index + 1}.</Text>
                      <Form.Item
                        {...field}
                        noStyle
                        rules={[{ required: true, message: '请填写步骤内容' }]}
                      >
                        <Input style={{ width: 600 }} placeholder="描述一个操作步骤" />
                      </Form.Item>
                      <Button
                        type="text"
                        danger
                        disabled={fields.length === 1}
                        onClick={() => remove(field.name)}
                      >
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button type="dashed" block onClick={() => add('')}>
                    + 添加步骤
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
          <Form.Item name="expected" label="预期结果">
            <TextArea rows={2} placeholder="执行完成后应看到的结果" />
          </Form.Item>
          <Form.Item name="trace_source" label="需求追溯">
            <Input placeholder="来自需求中的哪句话（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={activeCase?.title || '用例详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width="min(900px, 92vw)"
      >
        {activeCase && (
          <>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="模块">
                {activeCase.module || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="分类">
                <Tag color={CATEGORY_COLOR[activeCase.category]}>
                  {activeCase.category}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag color={PRIORITY_COLOR[activeCase.priority]}>
                  {activeCase.priority}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {activeCase.source === 'ai' ? 'AI 生成' : '手工创建'}
              </Descriptions.Item>
              <Descriptions.Item label="前置条件" span={2}>
                {activeCase.preconditions || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="需求追溯" span={2}>
                {activeCase.trace_source || '-'}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title="操作步骤" style={{ marginTop: 12 }}>
              <ol style={{ margin: 0, paddingLeft: 20 }}>
                {(activeCase.steps || []).map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </Card>

            <Card size="small" title="预期结果" style={{ marginTop: 12 }}>
              <Paragraph style={{ marginBottom: 0 }}>
                {activeCase.expected || '-'}
              </Paragraph>
            </Card>

            <Card
              size="small"
              title="登记执行结果"
              style={{ marginTop: 12 }}
              extra={
                <Tag color={activeCase.last_result ? RESULT_COLOR[activeCase.last_result] : 'default'}>
                  最近：{activeCase.last_result ? RESULT_LABEL[activeCase.last_result] : '未执行'}
                </Tag>
              }
            >
              <Form form={execForm} layout="vertical">
                <Row gutter={12}>
                  <Col span={8}>
                    <Form.Item
                      name="result"
                      label="执行结果"
                      rules={[{ required: true }]}
                    >
                      <Select options={RESULT_OPTIONS} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="run_label" label="轮次标签">
                      <Input placeholder="例如：round-1" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="defect_ref" label="缺陷单号">
                      <Input placeholder="可选" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="actual" label="实际结果">
                  <TextArea rows={2} placeholder="实际观察到的现象" />
                </Form.Item>
                <Form.Item name="remark" label="备注">
                  <Input placeholder="可选" />
                </Form.Item>
                <Button
                  type="primary"
                  loading={executing}
                  onClick={handleAddExecution}
                  icon={
                    execForm.getFieldValue('result') === 'failed' ? (
                      <CloseCircleOutlined />
                    ) : (
                      <CheckCircleOutlined />
                    )
                  }
                >
                  提交执行结果
                </Button>
              </Form>
            </Card>

            <Card
              size="small"
              title={`执行历史（${executions.length}）`}
              style={{ marginTop: 12 }}
            >
              {executions.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="还没有执行记录"
                />
              ) : (
                <List
                  size="small"
                  dataSource={executions}
                  renderItem={(item: any) => (
                    <List.Item>
                      <Space direction="vertical" size={0} style={{ width: '100%' }}>
                        <Space>
                          <Tag color={RESULT_COLOR[item.result]}>
                            {RESULT_LABEL[item.result] || item.result}
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {item.executed_at
                              ? new Date(item.executed_at).toLocaleString()
                              : ''}
                          </Text>
                          {item.run_label && <Tag>{item.run_label}</Tag>}
                          {item.defect_ref && (
                            <Tag color="red">缺陷 {item.defect_ref}</Tag>
                          )}
                        </Space>
                        {item.actual && (
                          <Text style={{ fontSize: 12 }}>实际：{item.actual}</Text>
                        )}
                        {item.remark && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            备注：{item.remark}
                          </Text>
                        )}
                      </Space>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </>
        )}
      </Drawer>
    </div>
  );
}
