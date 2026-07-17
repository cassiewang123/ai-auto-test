import { useEffect, useState } from 'react';
import {
  Card,
  Tabs,
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
  Radio,
  Descriptions,
  Alert,
  Typography,
  Switch,
} from 'antd';
import {
  RocketOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  ApiOutlined,
  BellOutlined,
  CodeOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  ciCdApi,
  WEBHOOK_EVENTS,
} from '../services/ciCdApi';
import type {
  WebhookConfig,
  WebhookConfigCreate,
  CiTriggerResult,
} from '../services/ciCdApi';
import { testPlanApi, testCaseApi, environmentApi } from '../services/api';
import type { TestCase, TestPlan, Environment } from '../types';

const { Text, Paragraph } = Typography;

const eventColor: Record<string, string> = {
  'test_run.completed': 'green',
  'test_run.failed': 'red',
  ping: 'blue',
};

export default function CiCdPage() {
  return (
    <Card
      title={
        <Space>
          <RocketOutlined />
          <span>CI/CD 集成</span>
        </Space>
      }
    >
      <Tabs
        defaultActiveKey="trigger"
        items={[
          {
            key: 'trigger',
            label: (
              <span>
                <ThunderboltOutlined /> 触发测试
              </span>
            ),
            children: <TriggerTab />,
          },
          {
            key: 'webhook',
            label: (
              <span>
                <BellOutlined /> Webhook 配置
              </span>
            ),
            children: <WebhookTab />,
          },
          {
            key: 'examples',
            label: (
              <span>
                <CodeOutlined /> 使用示例
              </span>
            ),
            children: <ExamplesTab />,
          },
        ]}
      />
    </Card>
  );
}

// ===========================================================================
// Tab 1: 触发测试
// ===========================================================================
function TriggerTab() {
  const [triggerMode, setTriggerMode] = useState<'plan' | 'cases'>('plan');
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [triggering, setTriggering] = useState(false);
  const [result, setResult] = useState<CiTriggerResult | null>(null);
  const [form] = Form.useForm();

  async function loadOptions() {
    try {
      const [planRes, caseRes, envRes] = await Promise.all([
        testPlanApi.list({ page: 1, page_size: 200 }),
        testCaseApi.list({ page: 1, page_size: 200 }),
        environmentApi.list({ page: 1, page_size: 100 }),
      ]);
      setPlans(planRes.data || []);
      setCases(caseRes.data || []);
      setEnvironments(envRes.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadOptions();
  }, []);

  async function handleTrigger() {
    try {
      const values = await form.validateFields();
      setTriggering(true);
      const payload: any = {
        environment_id: values.environment_id || null,
      };
      if (triggerMode === 'plan') {
        payload.plan_id = values.plan_id;
      } else {
        payload.case_ids = values.case_ids;
      }
      const res = await ciCdApi.trigger(payload);
      setResult(res.data);
      message.success('测试已触发');
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setTriggering(false);
    }
  }

  const statusColor: Record<string, string> = {
    passed: '#52c41a',
    failed: '#ff4d4f',
    error: '#faad14',
    running: '#1677ff',
  };

  return (
    <div>
      <Card
        type="inner"
        title={
          <Space>
            <ThunderboltOutlined />
            <span>手动触发测试执行</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Form form={form} layout="vertical" style={{ maxWidth: 640 }}>
          <Form.Item label="触发方式">
            <Radio.Group
              value={triggerMode}
              onChange={(e) => setTriggerMode(e.target.value)}
            >
              <Radio.Button value="plan">按测试计划</Radio.Button>
              <Radio.Button value="cases">按用例选择</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {triggerMode === 'plan' ? (
            <Form.Item
              name="plan_id"
              label="测试计划"
              rules={[{ required: true, message: '请选择测试计划' }]}
            >
              <Select
                placeholder="选择测试计划"
                showSearch
                optionFilterProp="label"
                options={plans.map((p) => ({ label: p.name, value: p.id }))}
              />
            </Form.Item>
          ) : (
            <Form.Item
              name="case_ids"
              label="测试用例"
              rules={[{ required: true, message: '请至少选择一个用例' }]}
            >
              <Select
                mode="multiple"
                placeholder="选择要执行的用例"
                showSearch
                optionFilterProp="label"
                options={cases.map((c) => ({
                  label: `${c.title} [${c.method}]`,
                  value: c.id,
                }))}
                maxTagCount="responsive"
              />
            </Form.Item>
          )}

          <Form.Item name="environment_id" label="执行环境（可选）">
            <Select
              allowClear
              placeholder="选择环境变量集"
              showSearch
              optionFilterProp="label"
              options={environments.map((e) => ({
                label: e.name,
                value: e.id,
              }))}
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={triggering}
              onClick={handleTrigger}
            >
              触发执行
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {result && (
        <Card type="inner" title="触发结果">
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="状态">
              <Badge
                color={statusColor[result.status] || '#d9d9d9'}
                text={result.status || '-'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="Run ID">
              <Text code copyable>
                {result.run_id}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="总数">{result.total}</Descriptions.Item>
            <Descriptions.Item label="通过">
              <span style={{ color: '#52c41a' }}>{result.passed}</span>
            </Descriptions.Item>
            <Descriptions.Item label="失败">
              <span style={{ color: '#ff4d4f' }}>{result.failed}</span>
            </Descriptions.Item>
            <Descriptions.Item label="错误">
              <span style={{ color: '#faad14' }}>{result.error}</span>
            </Descriptions.Item>
            <Descriptions.Item label="消息" span={2}>
              {result.message || '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}
    </div>
  );
}

// ===========================================================================
// Tab 2: Webhook 配置
// ===========================================================================
function WebhookTab() {
  const [data, setData] = useState<WebhookConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WebhookConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [testResultOpen, setTestResultOpen] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const res = await ciCdApi.listWebhooks();
      setData(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ events: [], is_active: true });
    setModalOpen(true);
  }

  function openEdit(record: WebhookConfig) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      url: record.url,
      events: record.events || [],
      secret: '',
      is_active: record.is_active,
      project_id: record.project_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload: WebhookConfigCreate = {
        name: values.name,
        url: values.url,
        events: values.events || [],
        is_active: values.is_active ?? true,
        project_id: values.project_id || null,
      };
      // 仅在填写了 secret 时才传递（编辑时不填表示保持原值）
      if (values.secret) {
        payload.secret = values.secret;
      }
      if (editing) {
        await ciCdApi.updateWebhook(editing.id, payload);
        message.success('更新成功');
      } else {
        await ciCdApi.createWebhook(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await ciCdApi.deleteWebhook(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleTest(id: string) {
    setTestingId(id);
    try {
      const res = await ciCdApi.testWebhook(id);
      setTestResult(res.data);
      setTestResultOpen(true);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setTestingId(null);
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name', width: 160, ellipsis: true },
    {
      title: 'URL',
      dataIndex: 'url',
      ellipsis: true,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '事件',
      dataIndex: 'events',
      width: 240,
      render: (events: string[]) => (
        <Space size={[4, 4]} wrap>
          {(events || []).map((ev) => (
            <Tag key={ev} color={eventColor[ev] || 'default'}>
              {ev}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '密钥',
      width: 80,
      render: (_: any, record: WebhookConfig) =>
        record.has_secret ? <Tag color="gold">已设置</Tag> : <Tag>无</Tag>,
    },
    {
      title: '状态',
      width: 90,
      render: (_: any, record: WebhookConfig) => (
        <Badge
          status={record.is_active ? 'success' : 'default'}
          text={record.is_active ? '启用' : '已禁用'}
        />
      ),
    },
    {
      title: '操作',
      width: 220,
      render: (_: any, record: WebhookConfig) => (
        <Space>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<PlayCircleOutlined />}
            loading={testingId === record.id}
            onClick={() => handleTest(record.id)}
          >
            测试
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除该 Webhook？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
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
        type="inner"
        title={
          <Space>
            <BellOutlined />
            <span>Webhook 配置</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {data.length} 个
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建 Webhook
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={data}
          rowKey="id"
          loading={loading}
          pagination={false}
          columns={columns}
          size="middle"
          locale={{ emptyText: <Empty description="暂无 Webhook 配置" /> }}
        />
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑 Webhook' : '新建 Webhook'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={{ events: [], is_active: true }}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：Jenkins 通知" />
          </Form.Item>

          <Form.Item
            name="url"
            label="Webhook URL"
            rules={[
              { required: true, message: '请输入 URL' },
              { type: 'url', message: '请输入有效的 URL' },
            ]}
          >
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>

          <Form.Item
            name="events"
            label="订阅事件"
            rules={[{ required: true, message: '请至少选择一个事件' }]}
          >
            <Select
              mode="multiple"
              placeholder="选择要订阅的事件"
              options={WEBHOOK_EVENTS.map((ev) => ({ label: ev, value: ev }))}
              maxTagCount="responsive"
            />
          </Form.Item>

          <Form.Item
            name="secret"
            label="签名密钥（可选）"
            extra={
              editing ? (
                <span style={{ color: '#6b7280' }}>
                  留空表示不修改原有密钥
                </span>
              ) : (
                <span style={{ color: '#6b7280' }}>
                  用于 HMAC-SHA256 签名验证，通过 X-Airetest-Signature 头传递
                </span>
              )
            }
          >
            <Input.Password placeholder="输入密钥用于签名校验" />
          </Form.Item>

          <Form.Item name="is_active" label="是否启用" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 测试结果 Modal */}
      <Modal
        title="Webhook 测试结果"
        open={testResultOpen}
        onCancel={() => setTestResultOpen(false)}
        footer={
          <Button type="primary" onClick={() => setTestResultOpen(false)}>
            关闭
          </Button>
        }
        width={560}
      >
        {testResult && (
          <div>
            <Alert
              type={testResult.sent ? 'success' : 'warning'}
              showIcon
              title={testResult.sent ? '测试请求已发送' : '测试请求未成功发送'}
              style={{ marginBottom: 12 }}
            />
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="Webhook ID">
                {testResult.webhook_id}
              </Descriptions.Item>
              <Descriptions.Item label="已发送">
                {testResult.sent ? '是' : '否'}
              </Descriptions.Item>
              {testResult.results && testResult.results.length > 0 && (
                <Descriptions.Item label="响应详情">
                  <pre style={{ margin: 0, fontSize: 12 }}>
                    {JSON.stringify(testResult.results, null, 2)}
                  </pre>
                </Descriptions.Item>
              )}
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  );
}

// ===========================================================================
// Tab 3: 使用示例（curl 命令）
// ===========================================================================
function ExamplesTab() {
  const curlTrigger = `curl -X POST http://your-host/api/v1/ci/trigger \\
  -H "Authorization: Bearer air_your_token_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "plan_id": "your-plan-id",
    "environment_id": "your-env-id"
  }'`;

  const curlTriggerCases = `curl -X POST http://your-host/api/v1/ci/trigger \\
  -H "X-API-Key: air_your_token_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "case_ids": ["case-id-1", "case-id-2"]
  }'`;

  const curlStatus = `curl http://your-host/api/v1/ci/runs/{run_id}/status \\
  -H "Authorization: Bearer air_your_token_here"`;

  return (
    <div>
      <Alert
        type="info"
        showIcon
        title="CI/CD 集成说明"
        description="通过 API Token 可以在 CI/CD 流水线中触发测试执行并查询结果。Token 支持通过 Authorization: Bearer 或 X-API-Key 两种方式传递。"
        style={{ marginBottom: 16 }}
      />

      <Card
        type="inner"
        title={<Space><ApiOutlined /><span>1. 触发测试（按计划）</span></Space>}
        style={{ marginBottom: 16 }}
      >
        <Paragraph>
          <pre
            style={{
              background: '#1e293b',
              color: '#e2e8f0',
              padding: 16,
              borderRadius: 8,
              overflow: 'auto',
              fontSize: 13,
              margin: 0,
            }}
          >
            {curlTrigger}
          </pre>
        </Paragraph>
      </Card>

      <Card
        type="inner"
        title={<Space><ApiOutlined /><span>2. 触发测试（按用例，使用 X-API-Key）</span></Space>}
        style={{ marginBottom: 16 }}
      >
        <Paragraph>
          <pre
            style={{
              background: '#1e293b',
              color: '#e2e8f0',
              padding: 16,
              borderRadius: 8,
              overflow: 'auto',
              fontSize: 13,
              margin: 0,
            }}
          >
            {curlTriggerCases}
          </pre>
        </Paragraph>
      </Card>

      <Card
        type="inner"
        title={<Space><ApiOutlined /><span>3. 查询执行状态</span></Space>}
      >
        <Paragraph>
          <pre
            style={{
              background: '#1e293b',
              color: '#e2e8f0',
              padding: 16,
              borderRadius: 8,
              overflow: 'auto',
              fontSize: 13,
              margin: 0,
            }}
          >
            {curlStatus}
          </pre>
        </Paragraph>
        <Text type="secondary">
          注意：plan_id 与 case_ids 互斥，只能传其中一个。environment_id 为可选参数。
        </Text>
      </Card>
    </div>
  );
}
