import { useEffect, useState } from 'react';
import {
  Tabs,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  message,
  Popconfirm,
  Tag,
  Switch,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import type { ApiResponse, PageResponse, Project } from '../types';
import { projectApi } from '../services/api';

const { TextArea } = Input;

// ---------------------------------------------------------------------------
// 本地 axios 实例（通知 API 未集成到 services/api.ts，由集成阶段统一处理）
// ---------------------------------------------------------------------------
const notifApi = axios.create({
  baseURL: '/api/v1/notifications',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});
notifApi.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.message || error.message || '请求失败';
    return Promise.reject(new Error(msg));
  }
);

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------
interface NotificationChannel {
  id: string;
  name: string;
  type: string;
  webhook_url: string;
  has_url: boolean;
  has_secret: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface NotificationRule {
  id: string;
  name: string;
  channel_id: string;
  event_type: string;
  project_id: string | null;
  filters: Record<string, any> | null;
  is_active: boolean;
  created_at: string;
  channel_name: string | null;
}

interface NotificationLog {
  id: string;
  channel_name: string | null;
  event_type: string;
  status: string;
  message: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// 常量映射
// ---------------------------------------------------------------------------
const CHANNEL_TYPE_OPTIONS = [
  { label: '飞书', value: 'feishu' },
  { label: '钉钉', value: 'dingtalk' },
  { label: '企微', value: 'wechat' },
  { label: 'Slack', value: 'slack' },
];

const CHANNEL_TYPE_COLOR: Record<string, string> = {
  feishu: 'blue',
  dingtalk: 'gold',
  wechat: 'green',
  slack: 'purple',
};

const CHANNEL_TYPE_LABEL: Record<string, string> = {
  feishu: '飞书',
  dingtalk: '钉钉',
  wechat: '企微',
  slack: 'Slack',
};

const EVENT_TYPE_OPTIONS = [
  { label: '测试执行完成', value: 'test_run.completed' },
  { label: '测试执行失败', value: 'test_run.failed' },
  { label: '定时任务完成', value: 'scheduled_task.completed' },
  { label: '性能测试完成', value: 'perf_test.completed' },
];

const EVENT_TYPE_LABEL: Record<string, string> = {
  'test_run.completed': '测试执行完成',
  'test_run.failed': '测试执行失败',
  'scheduled_task.completed': '定时任务完成',
  'perf_test.completed': '性能测试完成',
  test: '测试通知',
};

// Webhook URL 脱敏
function maskUrl(url: string): string {
  if (!url) return '-';
  if (url.length <= 40) return url;
  return url.slice(0, 30) + '****' + url.slice(-8);
}

// ===========================================================================
// 渠道 Tab
// ===========================================================================
function ChannelsTab() {
  const [data, setData] = useState<NotificationChannel[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await notifApi.get<unknown, PageResponse<NotificationChannel>>(
        '/channels',
        { params: { page: p, page_size: ps } }
      );
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true, type: 'feishu' });
    setModalOpen(true);
  }

  function openEdit(record: NotificationChannel) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      type: record.type,
      webhook_url: record.webhook_url,
      secret: '',
      is_active: record.is_active,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      if (editing) {
        await notifApi.put(`/channels/${editing.id}`, values);
        message.success('更新成功');
      } else {
        await notifApi.post('/channels', values);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    }
  }

  async function handleDelete(id: string) {
    try {
      await notifApi.delete(`/channels/${id}`);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleToggle(record: NotificationChannel, checked: boolean) {
    try {
      await notifApi.put(`/channels/${record.id}`, { is_active: checked });
      message.success(checked ? '已启用' : '已禁用');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleTest(id: string) {
    setTesting(id);
    try {
      const res = await notifApi.post<unknown, ApiResponse<{ success: boolean; message: string }>>(
        `/channels/${id}/test`
      );
      if (res.data.success) {
        message.success('测试通知发送成功');
      } else {
        message.error(`发送失败：${res.data.message}`);
      }
      // 刷新日志可能需要，此处不强制
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setTesting(null);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
          刷新
        </Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建渠道
        </Button>
      </div>

      <Table
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
            loadData(p, ps);
          },
        }}
        columns={[
          { title: '名称', dataIndex: 'name', width: 160 },
          {
            title: '类型',
            dataIndex: 'type',
            width: 90,
            render: (v: string) => (
              <Tag color={CHANNEL_TYPE_COLOR[v] || 'default'}>
                {CHANNEL_TYPE_LABEL[v] || v}
              </Tag>
            ),
          },
          {
            title: 'Webhook URL',
            dataIndex: 'webhook_url',
            ellipsis: true,
            render: (v: string) => (
              <Tooltip title={v}>
                <span>{maskUrl(v)}</span>
              </Tooltip>
            ),
          },
          {
            title: '加签密钥',
            width: 100,
            render: (_: unknown, record: NotificationChannel) =>
              record.has_secret ? <Tag>已配置</Tag> : '-',
          },
          {
            title: '状态',
            dataIndex: 'is_active',
            width: 80,
            render: (v: boolean, record) => (
              <Switch
                checked={v}
                size="small"
                onChange={(checked) => handleToggle(record, checked)}
              />
            ),
          },
          {
            title: '操作',
            width: 220,
            render: (_, record) => (
              <Space>
                <Button
                  size="small"
                  icon={<ExperimentOutlined />}
                  loading={testing === record.id}
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
                  title="确认删除？"
                  onConfirm={() => handleDelete(record.id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '编辑渠道' : '新建渠道'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="渠道名称"
            rules={[{ required: true, message: '请输入渠道名称' }]}
          >
            <Input placeholder="如：飞书测试群机器人" />
          </Form.Item>
          <Form.Item
            name="type"
            label="渠道类型"
            rules={[{ required: true, message: '请选择渠道类型' }]}
          >
            <Select options={CHANNEL_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="webhook_url"
            label="Webhook URL"
            rules={[{ required: true, message: '请输入 Webhook URL' }]}
          >
            <Input placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx" />
          </Form.Item>
          <Form.Item
            name="secret"
            label="加签密钥（可选）"
            extra="飞书/钉钉机器人加签密钥，未启用加签则留空"
          >
            <Input.Password placeholder="SEC..." />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ===========================================================================
// 规则 Tab
// ===========================================================================
function RulesTab() {
  const [data, setData] = useState<NotificationRule[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationRule | null>(null);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await notifApi.get<unknown, PageResponse<NotificationRule>>(
        '/rules',
        { params: { page: p, page_size: ps } }
      );
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadOptions() {
    try {
      const [chRes, projRes] = await Promise.all([
        notifApi.get<unknown, PageResponse<NotificationChannel>>('/channels', {
          params: { page: 1, page_size: 100 },
        }),
        projectApi.listAll(),
      ]);
      setChannels(chRes.data || []);
      setProjects(projRes.data || []);
    } catch {
      // 忽略选项加载失败
    }
  }

  useEffect(() => {
    loadData(1);
    loadOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true, event_type: 'test_run.completed' });
    setModalOpen(true);
  }

  function openEdit(record: NotificationRule) {
    setEditing(record);
    form.setFieldsValue({
      ...record,
      filters: record.filters ? JSON.stringify(record.filters, null, 2) : '',
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      let filters = null;
      if (values.filters) {
        try {
          filters = JSON.parse(values.filters);
        } catch {
          message.error('过滤条件 JSON 格式不正确');
          return;
        }
      }
      const payload = { ...values, filters, project_id: values.project_id || null };
      if (editing) {
        await notifApi.put(`/rules/${editing.id}`, payload);
        message.success('更新成功');
      } else {
        await notifApi.post('/rules', payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    }
  }

  async function handleDelete(id: string) {
    try {
      await notifApi.delete(`/rules/${id}`);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
          刷新
        </Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建规则
        </Button>
      </div>

      <Table
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
            loadData(p, ps);
          },
        }}
        columns={[
          { title: '名称', dataIndex: 'name', width: 160 },
          { title: '渠道', dataIndex: 'channel_name', width: 140 },
          {
            title: '事件类型',
            dataIndex: 'event_type',
            width: 140,
            render: (v: string) => EVENT_TYPE_LABEL[v] || v,
          },
          {
            title: '状态',
            dataIndex: 'is_active',
            width: 80,
            render: (v: boolean) =>
              v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>,
          },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 180,
            render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
          },
          {
            title: '操作',
            width: 150,
            render: (_, record) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openEdit(record)}
                >
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除？"
                  onConfirm={() => handleDelete(record.id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '编辑规则' : '新建规则'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="规则名称"
            rules={[{ required: true, message: '请输入规则名称' }]}
          >
            <Input placeholder="如：测试失败通知" />
          </Form.Item>
          <Form.Item
            name="channel_id"
            label="通知渠道"
            rules={[{ required: true, message: '请选择通知渠道' }]}
          >
            <Select
              placeholder="选择渠道"
              options={channels.map((c) => ({
                label: `${c.name}（${CHANNEL_TYPE_LABEL[c.type] || c.type}）`,
                value: c.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="event_type"
            label="事件类型"
            rules={[{ required: true, message: '请选择事件类型' }]}
          >
            <Select options={EVENT_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="project_id" label="关联项目（可选）">
            <Select
              allowClear
              placeholder="不选则所有项目"
              options={projects.map((p) => ({
                label: p.name,
                value: p.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="filters"
            label="过滤条件（JSON，可选）"
            extra='如 {"min_failure_rate": 0.1}'
          >
            <TextArea rows={3} placeholder='{"min_failure_rate": 0.1}' />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ===========================================================================
// 日志 Tab
// ===========================================================================
function LogsTab() {
  const [data, setData] = useState<NotificationLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [filterChannel, setFilterChannel] = useState<string>('');
  const [filterEvent, setFilterEvent] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');

  async function loadData(
    p = page,
    ps = pageSize,
    channel = filterChannel,
    event = filterEvent,
    status = filterStatus
  ) {
    setLoading(true);
    try {
      const params: Record<string, any> = { page: p, page_size: ps };
      if (channel) params.channel_id = channel;
      if (event) params.event_type = event;
      if (status) params.status = status;
      const res = await notifApi.get<unknown, PageResponse<NotificationLog>>(
        '/logs',
        { params }
      );
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData(1);
    // 加载渠道列表用于筛选
    notifApi
      .get<unknown, PageResponse<NotificationChannel>>('/channels', {
        params: { page: 1, page_size: 100 },
      })
      .then((res) => setChannels(res.data || []))
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Select
          allowClear
          placeholder="按渠道筛选"
          style={{ width: 180 }}
          value={filterChannel || undefined}
          onChange={(v) => setFilterChannel(v || '')}
          options={channels.map((c) => ({ label: c.name, value: c.id }))}
        />
        <Select
          allowClear
          placeholder="按状态筛选"
          style={{ width: 140 }}
          value={filterStatus || undefined}
          onChange={(v) => setFilterStatus(v || '')}
          options={[
            { label: '成功', value: 'success' },
            { label: '失败', value: 'failed' },
          ]}
        />
        <Select
          allowClear
          placeholder="按事件类型筛选"
          style={{ width: 180 }}
          value={filterEvent || undefined}
          onChange={(v) => setFilterEvent(v || '')}
          options={EVENT_TYPE_OPTIONS.concat([
            { label: '测试通知', value: 'test' },
          ])}
        />
        <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
          刷新
        </Button>
      </div>

      <Table
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
            loadData(p, ps);
          },
        }}
        columns={[
          {
            title: '时间',
            dataIndex: 'created_at',
            width: 180,
            render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
          },
          { title: '渠道', dataIndex: 'channel_name', width: 140 },
          {
            title: '事件类型',
            dataIndex: 'event_type',
            width: 140,
            render: (v: string) => EVENT_TYPE_LABEL[v] || v,
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 90,
            render: (v: string) =>
              v === 'success' ? (
                <Tag color="green">成功</Tag>
              ) : (
                <Tag color="red">失败</Tag>
              ),
          },
          {
            title: '消息',
            dataIndex: 'message',
            ellipsis: true,
          },
        ]}
      />
    </div>
  );
}

// ===========================================================================
// 主页面
// ===========================================================================
export default function NotificationsPage() {
  return (
    <Tabs
      defaultActiveKey="channels"
      items={[
        {
          key: 'channels',
          label: '通知渠道',
          children: <ChannelsTab />,
        },
        {
          key: 'rules',
          label: '通知规则',
          children: <RulesTab />,
        },
        {
          key: 'logs',
          label: '通知日志',
          children: <LogsTab />,
        },
      ]}
    />
  );
}
