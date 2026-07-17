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
  Badge,
  Empty,
  Alert,
  Typography,
  DatePicker,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  KeyOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { apiTokenApi, TOKEN_SCOPES } from '../services/ciCdApi';
import type { ApiToken, ApiTokenCreateResult } from '../services/ciCdApi';

const { Text, Paragraph } = Typography;

const scopeColor: Record<string, string> = {
  'test-cases:execute': 'blue',
  'test-plans:execute': 'cyan',
  'ci:trigger': 'purple',
};

export default function ApiTokensPage() {
  const [data, setData] = useState<ApiToken[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 一次性明文 token 展示
  const [createdToken, setCreatedToken] = useState<ApiTokenCreateResult | null>(null);
  const [tokenModalOpen, setTokenModalOpen] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const res = await apiTokenApi.list();
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
    form.resetFields();
    form.setFieldsValue({ scopes: [] });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload = {
        name: values.name,
        scopes: values.scopes || [],
        expires_at: values.expires_at ? values.expires_at.toISOString() : null,
      };
      const res = await apiTokenApi.create(payload);
      message.success('Token 创建成功');
      setModalOpen(false);
      setCreatedToken(res.data);
      setTokenModalOpen(true);
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
      await apiTokenApi.delete(id);
      message.success('Token 已吊销');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  function copyToken(token: string) {
    navigator.clipboard.writeText(token).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败，请手动复制')
    );
  }

  const columns = [
    { title: '名称', dataIndex: 'name', width: 180, ellipsis: true },
    {
      title: 'Token',
      dataIndex: 'token_masked',
      width: 220,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: 'Scopes',
      dataIndex: 'scopes',
      width: 280,
      render: (scopes: string[]) => (
        <Space size={[4, 4]} wrap>
          {(scopes || []).map((s) => (
            <Tag key={s} color={scopeColor[s] || 'default'}>
              {s}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态',
      width: 90,
      render: (_: any, record: ApiToken) => (
        <Badge
          status={record.is_active ? 'success' : 'default'}
          text={record.is_active ? '启用' : '已禁用'}
        />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
    },
    {
      title: '最后使用',
      dataIndex: 'last_used_at',
      width: 170,
      render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '从未使用'),
    },
    {
      title: '操作',
      width: 100,
      render: (_: any, record: ApiToken) => (
        <Popconfirm
          title="确认吊销该 Token？"
          description="吊销后使用该 Token 的请求将立即失效，且不可恢复。"
          onConfirm={() => handleDelete(record.id)}
        >
          <Button size="small" danger icon={<DeleteOutlined />}>
            吊销
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <KeyOutlined />
            <span>API Token 管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {data.length} 个 Token
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建 Token
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
          locale={{ emptyText: <Empty description="暂无 API Token" /> }}
        />
      </Card>

      {/* 新建 Token Modal */}
      <Modal
        title="新建 API Token"
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={{ scopes: [] }}>
          <Form.Item
            name="name"
            label="Token 名称"
            rules={[{ required: true, message: '请输入 Token 名称' }]}
          >
            <Input placeholder="如：CI 流水线专用" />
          </Form.Item>

          <Form.Item
            name="scopes"
            label="权限范围（Scopes）"
            rules={[{ required: true, message: '请至少选择一个权限' }]}
          >
            <Select
              mode="multiple"
              placeholder="选择该 Token 可使用的权限"
              options={TOKEN_SCOPES.map((s) => ({ label: s, value: s }))}
              maxTagCount="responsive"
            />
          </Form.Item>

          <Form.Item name="expires_at" label="过期时间（可选）">
            <DatePicker
              showTime
              style={{ width: '100%' }}
              placeholder="不选则永不过期"
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 一次性明文 Token 展示 Modal */}
      <Modal
        title="Token 已创建"
        open={tokenModalOpen}
        onCancel={() => setTokenModalOpen(false)}
        footer={
          <Button type="primary" onClick={() => setTokenModalOpen(false)}>
            我已保存
          </Button>
        }
        width={600}
        destroyOnHidden
      >
        {createdToken && (
          <div>
            <Alert
              type="warning"
              showIcon
              title="请立即保存此 Token"
              description="完整 Token 仅在此次创建时显示一次，关闭后将无法再次查看。请妥善保管。"
              style={{ marginBottom: 16 }}
            />
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">名称：</Text>
              <Text strong>{createdToken.name}</Text>
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">完整 Token：</Text>
            </div>
            <Paragraph
              copyable
              code
              style={{
                background: '#f5f5f5',
                padding: '8px 12px',
                borderRadius: 6,
                wordBreak: 'break-all',
                margin: 0,
              }}
            >
              {createdToken.token}
            </Paragraph>
            <div style={{ marginTop: 12 }}>
              <Button
                icon={<CopyOutlined />}
                onClick={() => copyToken(createdToken.token)}
              >
                复制 Token
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
