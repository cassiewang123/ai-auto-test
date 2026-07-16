import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Divider,
  Space,
  message,
  Popconfirm,
  Tag,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { environmentApi } from '../services/api';
import type { Environment, EnvironmentCreate } from '../types';

const { TextArea } = Input;

// 校验 Base URL 是否为 IP 地址格式（如 http://192.168.1.1:8080）
function isValidIpUrl(url: string): boolean {
  if (!url) return false;
  const re = /^https?:\/\/(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(:\d+)?(\/.*)?$/;
  const m = url.match(re);
  if (!m) return false;
  // 校验每个 IP 段在 0-255 之间
  return [m[1], m[2], m[3], m[4]].every((seg) => {
    const n = Number(seg);
    return n >= 0 && n <= 255;
  });
}

export default function EnvironmentsPage() {
  const [data, setData] = useState<Environment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [searchName, setSearchName] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Environment | null>(null);
  const [form] = Form.useForm();

  // Cookie 管理
  const [cookies, setCookies] = useState<Environment['cookies']>([]);
  const [cookieModalOpen, setCookieModalOpen] = useState(false);
  const [editingCookieIdx, setEditingCookieIdx] = useState<number | null>(null);
  const [cookieForm] = Form.useForm();

  async function loadData(p = page, ps = pageSize, name = searchName) {
    setLoading(true);
    try {
      const res = await environmentApi.list({ page: p, page_size: ps, name });
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
    form.setFieldsValue({
      is_active: true,
      variables: '{}',
      db_type: 'mysql',
      db_host: '',
      db_port: 3306,
      db_database: '',
      db_user: '',
      db_password: '',
    });
    setCookies([]);
    setModalOpen(true);
  }

  function openEdit(record: Environment) {
    setEditing(record);
    const cfg = record.db_config || {};
    form.setFieldsValue({
      ...record,
      variables: JSON.stringify(record.variables || {}, null, 2),
      db_type: cfg.db_type || 'mysql',
      db_host: cfg.host || '',
      db_port: cfg.port ?? 3306,
      db_database: cfg.database || '',
      db_user: cfg.user || '',
      db_password: cfg.password || '',
    });
    setCookies(record.cookies || []);
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      // 前端 IP 格式校验
      if (!isValidIpUrl(values.base_url)) {
        message.error('Base URL 仅支持 IP 地址格式（如 http://192.168.1.1:8080）');
        return;
      }
      let variables = {};
      try {
        variables = values.variables ? JSON.parse(values.variables) : {};
      } catch {
        message.error('变量 JSON 格式不正确');
        return;
      }
      // 打包数据库配置：仅在填写了关键字段时才提交 db_config
      let db_config: EnvironmentCreate['db_config'] = null;
      if (values.db_database || values.db_host) {
        db_config = {
          db_type: values.db_type || 'mysql',
          host: values.db_host || undefined,
          port: values.db_port ?? undefined,
          database: values.db_database || undefined,
          user: values.db_user || undefined,
          password: values.db_password || undefined,
        };
      }
      const payload: EnvironmentCreate = {
        name: values.name,
        base_url: values.base_url,
        description: values.description,
        variables,
        db_config,
        cookies: cookies && cookies.length > 0 ? cookies : undefined,
      };
      if (editing) {
        await environmentApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await environmentApi.create(payload);
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
      await environmentApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // ---- Cookie 管理 ----
  function openCookieCreate() {
    setEditingCookieIdx(null);
    cookieForm.resetFields();
    cookieForm.setFieldsValue({ path: '/', domain: '' });
    setCookieModalOpen(true);
  }

  function openCookieEdit(idx: number) {
    setEditingCookieIdx(idx);
    const c = cookies![idx];
    cookieForm.setFieldsValue({
      name: c.name,
      value: c.value,
      domain: c.domain || '',
      path: c.path || '/',
    });
    setCookieModalOpen(true);
  }

  async function handleCookieSubmit() {
    try {
      const values = await cookieForm.validateFields();
      const cookie: NonNullable<Environment['cookies']>[number] = {
        name: values.name,
        value: values.value,
        domain: values.domain || undefined,
        path: values.path || undefined,
      };
      if (editingCookieIdx !== null) {
        const next = [...(cookies || [])];
        next[editingCookieIdx] = cookie;
        setCookies(next);
      } else {
        setCookies([...(cookies || []), cookie]);
      }
      setCookieModalOpen(false);
    } catch (e: any) {
      if (e.errorFields) return;
    }
  }

  function handleCookieDelete(idx: number) {
    setCookies((cookies || []).filter((_, i) => i !== idx));
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Input.Search
            placeholder="搜索环境名称"
            allowClear
            style={{ width: 240 }}
            onSearch={(v) => {
              setSearchName(v);
              setPage(1);
              loadData(1, pageSize, v);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
            刷新
          </Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-testid="create-env-btn">
          新建环境
        </Button>
      </div>

      <Table
        dataSource={data}
        rowKey="id"
        loading={loading}
        data-testid="env-table"
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
          { title: '名称', dataIndex: 'name', width: 150 },
          { title: 'Base URL', dataIndex: 'base_url', ellipsis: true },
          { title: '描述', dataIndex: 'description', ellipsis: true },
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
            render: (t: string) => new Date(t).toLocaleString('zh-CN'),
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
        title={editing ? '编辑环境' : '新建环境'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="环境名称"
            rules={[{ required: true, message: '请输入环境名称' }]}
          >
            <Input placeholder="如：dev / staging / prod" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[
              { required: true, message: '请输入 Base URL' },
              {
                validator: (_, value) =>
                  !value || isValidIpUrl(value)
                    ? Promise.resolve()
                    : Promise.reject(
                        new Error('仅支持 IP 地址格式（如 http://192.168.1.1:8080）')
                      ),
              },
            ]}
            extra="仅支持 IP 地址格式（如 http://192.168.1.1:8080）"
          >
            <Input placeholder="http://192.168.1.1:8080" data-testid="base-url-input" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="环境描述（可选）" />
          </Form.Item>
          <Form.Item name="variables" label="环境变量（JSON）">
            <TextArea
              rows={4}
              placeholder='{"token": "xxx", "db_url": "mysql://..."}'
            />
          </Form.Item>

          <Divider titlePlacement="left" plain>
            数据库配置
          </Divider>
          <Form.Item name="db_type" label="数据库类型">
            <Select
              options={[
                { label: 'MySQL', value: 'mysql' },
                { label: 'SQLite', value: 'sqlite' },
                { label: 'PostgreSQL', value: 'postgres' },
              ]}
            />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="db_host" label="主机地址" style={{ flex: 1, minWidth: 240 }}>
              <Input placeholder="如 127.0.0.1（SQLite 可留空）" />
            </Form.Item>
            <Form.Item name="db_port" label="端口" style={{ width: 120 }}>
              <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="3306" />
            </Form.Item>
          </Space>
          <Form.Item name="db_database" label="数据库名">
            <Input placeholder="如 app_db（SQLite 可填文件路径）" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="db_user" label="用户名" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="如 root" />
            </Form.Item>
            <Form.Item name="db_password" label="密码" style={{ flex: 1, minWidth: 200 }}>
              <Input.Password placeholder="数据库密码" />
            </Form.Item>
          </Space>

          <Divider titlePlacement="left" plain>
            Cookie 管理
          </Divider>
          <div style={{ marginBottom: 8 }}>
            <Button icon={<PlusOutlined />} onClick={openCookieCreate} size="small">
              新增 Cookie
            </Button>
          </div>
          <Table
            dataSource={cookies || []}
            rowKey={(_, idx) => String(idx)}
            pagination={false}
            size="small"
            locale={{ emptyText: '暂无 Cookie' }}
            columns={[
              {
                title: '名称',
                dataIndex: 'name',
                width: 160,
                render: (v: string) => <code style={{ fontWeight: 600 }}>{v}</code>,
              },
              {
                title: '值',
                dataIndex: 'value',
                ellipsis: true,
                render: (v: string) => <code>{v}</code>,
              },
              {
                title: '域名',
                dataIndex: 'domain',
                width: 160,
                render: (v: string) => v || '-',
              },
              {
                title: '路径',
                dataIndex: 'path',
                width: 100,
                render: (v: string) => v || '-',
              },
              {
                title: '操作',
                width: 140,
                render: (_, _c, idx) => (
                  <Space>
                    <Button
                      size="small"
                      type="link"
                      icon={<EditOutlined />}
                      onClick={() => openCookieEdit(idx)}
                    >
                      编辑
                    </Button>
                    <Popconfirm title="确认删除该 Cookie？" onConfirm={() => handleCookieDelete(idx)}>
                      <Button size="small" type="link" danger icon={<DeleteOutlined />}>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title={editingCookieIdx !== null ? '编辑 Cookie' : '新增 Cookie'}
        open={cookieModalOpen}
        onOk={handleCookieSubmit}
        onCancel={() => setCookieModalOpen(false)}
        width={480}
        destroyOnClose
      >
        <Form form={cookieForm} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入 Cookie 名称' }]}
          >
            <Input placeholder="如 token" />
          </Form.Item>
          <Form.Item
            name="value"
            label="值"
            rules={[{ required: true, message: '请输入 Cookie 值' }]}
          >
            <Input placeholder="Cookie 值" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="domain" label="域名" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="如 .example.com（可选）" />
            </Form.Item>
            <Form.Item name="path" label="路径" style={{ flex: 1, minWidth: 160 }}>
              <Input placeholder="如 /（可选）" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
