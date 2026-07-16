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
  UserOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import { authApi, type UserInfo, type RoleInfo } from '../contexts/AuthContext';

export default function UsersPage() {
  const [data, setData] = useState<UserInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<UserInfo | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [roleUser, setRoleUser] = useState<UserInfo | null>(null);
  const [allRoles, setAllRoles] = useState<RoleInfo[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [roleSubmitting, setRoleSubmitting] = useState(false);

  async function loadData(p = page, ps = pageSize, kw = keyword) {
    setLoading(true);
    try {
      const res = await authApi.listUsers({ page: p, page_size: ps, keyword: kw });
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
    form.setFieldsValue({ is_active: true, is_superuser: false });
    setModalOpen(true);
  }

  function openEdit(record: UserInfo) {
    setEditing(record);
    form.setFieldsValue({
      username: record.username,
      email: record.email,
      is_active: record.is_active,
      is_superuser: record.is_superuser,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (editing) {
        const payload: Record<string, any> = {
          username: values.username,
          email: values.email,
          is_active: values.is_active,
          is_superuser: values.is_superuser,
        };
        if (values.password) {
          payload.password = values.password;
        }
        await authApi.updateUser(editing.id, payload);
        message.success('更新成功');
      } else {
        await authApi.createUser({
          username: values.username,
          email: values.email,
          password: values.password,
          is_active: values.is_active,
          is_superuser: values.is_superuser,
        });
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
      await authApi.deleteUser(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function openRoleModal(record: UserInfo) {
    setRoleUser(record);
    setSelectedRoleIds(record.roles.map((r) => r.id));
    try {
      const res = await authApi.listAllRoles();
      setAllRoles(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
    setRoleModalOpen(true);
  }

  async function handleAssignRoles() {
    if (!roleUser) return;
    setRoleSubmitting(true);
    try {
      await authApi.assignRoles(roleUser.id, selectedRoleIds);
      message.success('角色分配成功');
      setRoleModalOpen(false);
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRoleSubmitting(false);
    }
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <UserOutlined />
            <span>用户管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个用户
            </span>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索用户名/邮箱"
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
              新建用户
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
              title: '用户名',
              dataIndex: 'username',
              width: 140,
              render: (v: string) => <span style={{ fontWeight: 600 }}>{v}</span>,
            },
            { title: '邮箱', dataIndex: 'email', ellipsis: true },
            {
              title: '状态',
              dataIndex: 'is_active',
              width: 90,
              render: (v: boolean) =>
                v ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
            },
            {
              title: '超级管理员',
              dataIndex: 'is_superuser',
              width: 100,
              render: (v: boolean) =>
                v ? <Tag color="purple">是</Tag> : <Tag>否</Tag>,
            },
            {
              title: '角色',
              dataIndex: 'roles',
              render: (roles: RoleInfo[]) =>
                roles && roles.length
                  ? roles.map((r) => (
                      <Tag color="blue" key={r.id}>
                        {r.name}
                      </Tag>
                    ))
                  : '-',
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
              width: 280,
              render: (_, record) => (
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    ghost
                    icon={<SafetyOutlined />}
                    onClick={() => openRoleModal(record)}
                  >
                    分配角色
                  </Button>
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => openEdit(record)}
                  >
                    编辑
                  </Button>
                  <Popconfirm
                    title="确认删除该用户？"
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
        title={editing ? '编辑用户' : '新建用户'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={520}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="用户名" />
          </Form.Item>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input placeholder="email@example.com" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={
              editing
                ? []
                : [{ required: true, message: '请输入密码' }]
            }
            extra={editing ? '留空则不修改密码' : undefined}
          >
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="is_superuser"
            label="超级管理员"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`分配角色 - ${roleUser?.username || ''}`}
        open={roleModalOpen}
        onOk={handleAssignRoles}
        confirmLoading={roleSubmitting}
        onCancel={() => setRoleModalOpen(false)}
        width={480}
        destroyOnClose
      >
        <Form layout="vertical">
          <Form.Item label="选择角色">
            <Select
              mode="multiple"
              placeholder="选择要分配的角色"
              style={{ width: '100%' }}
              value={selectedRoleIds}
              onChange={setSelectedRoleIds}
              options={allRoles.map((r) => ({
                label: `${r.name}${r.is_active ? '' : '（已禁用）'}`,
                value: r.id,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
