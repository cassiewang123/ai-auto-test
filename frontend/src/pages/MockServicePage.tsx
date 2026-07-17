import { useEffect, useState } from 'react';
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
  Switch,
  Tooltip,
  Empty,
  InputNumber,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  BlockOutlined,
  CopyOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { mockApi, projectApi } from '../services/api';
import type { Project } from '../types';

const { TextArea } = Input;

const methodColor: Record<string, string> = {
  GET: 'blue',
  POST: 'green',
  PUT: 'orange',
  PATCH: 'gold',
  DELETE: 'red',
};

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

// 构建 Mock 访问地址
function buildMockUrl(path: string): string {
  const origin = window.location.origin;
  const cleanPath = (path || '').replace(/^\//, '');
  return `${origin}/api/v1/mock-service/mock/${cleanPath}`;
}

export default function MockServicePage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [projects, setProjects] = useState<Project[]>([]);

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await mockApi.list({ page: p, page_size: ps });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadProjects() {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadData(1);
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      method: 'GET',
      status_code: 200,
      delay_ms: 0,
      response_headers: '{\n  "Content-Type": "application/json"\n}',
      response_body: '{\n  \n}',
      is_enabled: true,
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      method: record.method,
      path: record.path,
      status_code: record.status_code,
      delay_ms: record.delay_ms ?? 0,
      response_headers:
        typeof record.response_headers === 'string'
          ? record.response_headers
          : JSON.stringify(record.response_headers || {}, null, 2),
      response_body:
        typeof record.response_body === 'string'
          ? record.response_body
          : JSON.stringify(record.response_body || {}, null, 2),
      project_id: record.project_id,
      is_enabled: record.is_enabled ?? true,
      description: record.description,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      // 校验 JSON
      let responseHeaders: any = {};
      let responseBody: any = {};
      try {
        responseHeaders = values.response_headers
          ? JSON.parse(values.response_headers)
          : {};
      } catch {
        message.error('响应头 JSON 格式不正确');
        setSaving(false);
        return;
      }
      try {
        // 响应体允许是任意 JSON 或纯文本
        if (values.response_body) {
          try {
            responseBody = JSON.parse(values.response_body);
          } catch {
            responseBody = values.response_body;
          }
        }
      } catch {
        responseBody = values.response_body;
      }
      const payload: any = {
        name: values.name,
        method: values.method,
        path: values.path,
        status_code: values.status_code,
        delay_ms: values.delay_ms ?? 0,
        response_headers: responseHeaders,
        response_body: responseBody,
        project_id: values.project_id || null,
        is_enabled: values.is_enabled ?? true,
        description: values.description,
      };
      if (editing) {
        await mockApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await mockApi.create(payload);
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
      await mockApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleToggle(record: any) {
    try {
      await mockApi.toggle(record.id);
      message.success(record.is_enabled ? '已禁用' : '已启用');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 监听路径变化以实时预览 Mock 访问地址
  const watchPath = Form.useWatch('path', form) || '';

  async function handleCopyUrl(path: string) {
    const url = buildMockUrl(path);
    try {
      await navigator.clipboard.writeText(url);
      message.success('已复制 Mock 地址');
    } catch {
      // 降级处理
      const textarea = document.createElement('textarea');
      textarea.value = url;
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        message.success('已复制 Mock 地址');
      } catch {
        message.error('复制失败，请手动复制');
      }
      document.body.removeChild(textarea);
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name', width: 150, ellipsis: true },
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (m: string) => <Tag color={methodColor[m] || 'default'}>{m}</Tag>,
    },
    { title: '路径', dataIndex: 'path', width: 180, ellipsis: true },
    {
      title: '状态码',
      dataIndex: 'status_code',
      width: 80,
      align: 'center' as const,
      render: (c: number) => c || '-',
    },
    {
      title: '延迟(ms)',
      dataIndex: 'delay_ms',
      width: 90,
      align: 'center' as const,
      render: (d: number) => d || 0,
    },
    {
      title: '启用状态',
      width: 90,
      render: (_: any, record: any) => (
        <Switch
          checked={!!record.is_enabled}
          checkedChildren="启用"
          unCheckedChildren="禁用"
          onChange={() => handleToggle(record)}
        />
      ),
    },
    {
      title: 'Mock 地址',
      width: 220,
      render: (_: any, record: any) => {
        const url = buildMockUrl(record.path);
        return (
          <Space>
            <Tooltip title={url}>
              <span
                style={{
                  color: '#2563eb',
                  fontSize: 12,
                  maxWidth: 160,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  display: 'inline-block',
                  verticalAlign: 'middle',
                }}
              >
                {url}
              </span>
            </Tooltip>
            <Button
              size="small"
              type="link"
              icon={<CopyOutlined />}
              onClick={() => handleCopyUrl(record.path)}
            />
          </Space>
        );
      },
    },
    {
      title: '操作',
      width: 160,
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除该 Mock 配置？"
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
        title={
          <Space>
            <BlockOutlined />
            <span>Mock 服务</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个配置
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建 Mock
            </Button>
          </Space>
        }
      >
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
          columns={columns}
          size="middle"
          locale={{ emptyText: <Empty description="暂无 Mock 配置" /> }}
        />
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑 Mock 配置' : '新建 Mock 配置'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={680}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            method: 'GET',
            status_code: 200,
            delay_ms: 0,
            is_enabled: true,
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：获取用户列表 Mock" />
          </Form.Item>

          <Space style={{ width: '100%' }} size="middle">
            <Form.Item
              name="method"
              label="请求方法"
              rules={[{ required: true, message: '请选择方法' }]}
            >
              <Select
                style={{ width: 140 }}
                options={METHODS.map((m) => ({ label: m, value: m }))}
              />
            </Form.Item>
            <Form.Item
              name="path"
              label="路径"
              rules={[{ required: true, message: '请输入路径' }]}
              style={{ flex: 1, minWidth: 420 }}
              extra={
                <span style={{ color: '#6b7280' }}>
                  如 <code>api/users</code>，访问地址：
                  {buildMockUrl(watchPath)}
                </span>
              }
            >
              <Input placeholder="api/users" prefix={<LinkOutlined />} />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size="middle">
            <Form.Item
              name="status_code"
              label="状态码"
              rules={[{ required: true, message: '请输入状态码' }]}
            >
              <InputNumber
                style={{ width: 140 }}
                min={100}
                max={599}
                placeholder="200"
              />
            </Form.Item>
            <Form.Item name="delay_ms" label="延迟(ms)" style={{ flex: 1, minWidth: 420 }}>
              <InputNumber
                style={{ width: '100%' }}
                min={0}
                placeholder="0"
              />
            </Form.Item>
          </Space>

          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              showSearch
              optionFilterProp="label"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>

          <Form.Item name="response_headers" label="响应头（JSON）">
            <TextArea
              rows={3}
              placeholder='{"Content-Type": "application/json"}'
            />
          </Form.Item>

          <Form.Item name="response_body" label="响应体（JSON 或文本）">
            <TextArea rows={6} placeholder='{"code": 0, "data": {}}' />
          </Form.Item>

          <Form.Item name="is_enabled" label="是否启用">
            <Select
              options={[
                { value: true, label: '启用' },
                { value: false, label: '禁用' },
              ]}
            />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input placeholder="Mock 描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
