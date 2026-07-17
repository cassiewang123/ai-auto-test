import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Space,
  message,
  Popconfirm,
  Tag,
  Card,
  Switch,
  Select,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import { authApi, type RoleInfo } from '../contexts/AuthContext';

const { TextArea } = Input;

// 常用权限预设，便于快速选择
const PERMISSION_PRESETS = [
  'user:read',
  'user:manage',
  'role:read',
  'role:manage',
  'project:read',
  'project:manage',
  'testcase:read',
  'testcase:manage',
];

export default function RolesPage() {
  const [data, setData] = useState<RoleInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RoleInfo | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize, kw = keyword) {
    setLoading(true);
    try {
      const res = await authApi.listRoles({
        page: p,
        page_size: ps,
        keyword: kw,
      });
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
    form.setFieldsValue({ is_active: true, permissions: [] });
    setModalOpen(true);
  }

  function openEdit(record: RoleInfo) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      permissions: record.permissions,
      is_active: record.is_active,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const payload = {
        name: values.name,
        description: values.description,
        permissions: values.permissions || [],
        is_active: values.is_active,
      };
      if (editing) {
        await authApi.updateRole(editing.id, payload);
        message.success('更新成功');
      } else {
        await authApi.createRole(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await authApi.deleteRole(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <SafetyOutlined />
            <span>角色管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个角色
            </span>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索角色名称"
              allowClear
              style={{ width: 240 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(v) => {
                setPage(1);
                loadData(1, pageSize, v);
              }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建角色
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
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
              loadData(p, ps);
            },
          }}
          columns={[
            {
              title: '角色名称',
              dataIndex: 'name',
              width: 160,
              render: (v: string) => (
                <span style={{ fontWeight: 600 }}>{v}</span>
              ),
            },
            {
              title: '描述',
              dataIndex: 'description',
              ellipsis: true,
              render: (v: string) => v || '-',
            },
            {
              title: '权限',
              dataIndex: 'permissions',
              render: (perms: string[]) =>
                perms && perms.length ? (
                  <Space wrap size={[4, 4]}>
                    {perms.map((p) => (
                      <Tag color="geekblue" key={p}>
                        {p}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  '-'
                ),
            },
            {
              title: '状态',
              dataIndex: 'is_active',
              width: 90,
              render: (v: boolean) =>
                v ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 180,
              render: (t: string) =>
                t ? new Date(t).toLocaleString('zh-CN') : '-',
            },
            {
              title: '操作',
              width: 200,
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
                    title="确认删除该角色？"
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
      </Card>

      <Modal
        title={editing ? '编辑角色' : '新建角色'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="角色名称"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input placeholder="如：测试工程师" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="角色描述（可选）" />
          </Form.Item>
          <Form.Item name="permissions" label="权限">
            <Select
              mode="tags"
              placeholder="输入或选择权限，如 user:read"
              style={{ width: '100%' }}
              tokenSeparators={[',', ' ']}
              options={PERMISSION_PRESETS.map((p) => ({ label: p, value: p }))}
            />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
