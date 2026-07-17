import { useEffect, useState } from 'react';
import {
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
  Card,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { knowledgeApi } from '../services/api';

const { TextArea } = Input;

// HTTP 方法选项
const METHOD_OPTIONS = [
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
  { label: 'HEAD', value: 'HEAD' },
  { label: 'OPTIONS', value: 'OPTIONS' },
];

// HTTP 方法对应的 Tag 颜色
const METHOD_COLOR: Record<string, string> = {
  GET: 'blue',
  POST: 'green',
  PUT: 'orange',
  PATCH: 'gold',
  DELETE: 'red',
  HEAD: 'default',
  OPTIONS: 'default',
};

// 将 knowledge_content 对象序列化为字符串用于编辑
function stringifyContent(content: any): string {
  if (content === null || content === undefined) return '';
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return '';
  }
}

export default function InterfaceKnowledgePage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [projectId, setProjectId] = useState<string | undefined>(undefined);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize, pid = projectId) {
    setLoading(true);
    try {
      const res = await knowledgeApi.listInterfaces({
        page: p,
        page_size: ps,
        project_id: pid,
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
    form.setFieldsValue({
      method: 'GET',
      tags: [],
      knowledge_content: '',
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      method: record.method,
      api_path: record.api_path,
      description: record.description,
      knowledge_content: stringifyContent(record.knowledge_content),
      tags: record.tags || [],
      project_id: record.project_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      // 解析 knowledge_content JSON
      let knowledgeContent: any = values.knowledge_content;
      if (typeof knowledgeContent === 'string' && knowledgeContent.trim()) {
        try {
          knowledgeContent = JSON.parse(knowledgeContent);
        } catch {
          message.error('knowledge_content 不是合法的 JSON');
          setSubmitting(false);
          return;
        }
      }
      const payload: any = {
        name: values.name,
        method: values.method,
        api_path: values.api_path,
        description: values.description,
        knowledge_content: knowledgeContent || {},
        tags: values.tags || [],
      };
      if (values.project_id) payload.project_id = values.project_id;

      if (editing) {
        await knowledgeApi.updateInterface(editing.id, payload);
        message.success('更新成功');
      } else {
        await knowledgeApi.createInterface(payload);
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
      await knowledgeApi.deleteInterface(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 客户端按名称/路径过滤
  const filteredData = keyword
    ? data.filter((item) => {
        const kw = keyword.toLowerCase();
        return (
          (item.name || '').toLowerCase().includes(kw) ||
          (item.api_path || '').toLowerCase().includes(kw)
        );
      })
    : data;

  return (
    <div>
      <Card
        title={
          <Space>
            <ApiOutlined />
            <span>接口知识库</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条
            </span>
          </Space>
        }
        extra={
          <Space wrap>
            <Input.Search
              placeholder="搜索名称/路径"
              allowClear
              style={{ width: 220 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(v) => setKeyword(v)}
            />
            <Input
              allowClear
              placeholder="项目 ID 筛选"
              style={{ width: 180 }}
              value={projectId || ''}
              onChange={(e) => setProjectId(e.target.value || undefined)}
              onPressEnter={() => {
                setPage(1);
                loadData(1, pageSize, projectId);
              }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={filteredData}
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
              title: '名称',
              dataIndex: 'name',
              width: 180,
              render: (v: string) => (
                <span style={{ fontWeight: 600 }}>{v}</span>
              ),
            },
            {
              title: '方法',
              dataIndex: 'method',
              width: 90,
              render: (v: string) =>
                v ? (
                  <Tag color={METHOD_COLOR[v] || 'default'}>{v}</Tag>
                ) : (
                  '-'
                ),
            },
            {
              title: '接口路径',
              dataIndex: 'api_path',
              ellipsis: true,
              render: (v: string) => (
                <code style={{ fontSize: 13 }}>{v || '-'}</code>
              ),
            },
            {
              title: '描述',
              dataIndex: 'description',
              ellipsis: true,
              render: (v: string) => v || '-',
            },
            {
              title: '标签',
              dataIndex: 'tags',
              width: 200,
              render: (tags: string[]) =>
                tags && tags.length ? (
                  <Space wrap size={[4, 4]}>
                    {tags.map((t) => (
                      <Tag color="geekblue" key={t}>
                        {t}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  '-'
                ),
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
              width: 180,
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
                    title="确认删除该接口知识？"
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

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editing ? '编辑接口知识' : '新建接口知识'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：用户登录接口" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item
              name="method"
              label="HTTP 方法"
              rules={[{ required: true, message: '请选择方法' }]}
              style={{ width: 180 }}
            >
              <Select options={METHOD_OPTIONS} placeholder="选择方法" />
            </Form.Item>
            <Form.Item
              name="api_path"
              label="接口路径"
              rules={[{ required: true, message: '请输入接口路径' }]}
              style={{ flex: 1, marginBottom: 24 }}
            >
              <Input placeholder="/api/v1/users/login" />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="接口描述（可选）" />
          </Form.Item>
          <Form.Item
            name="knowledge_content"
            label="知识内容（JSON）"
            tooltip="请输入合法 JSON，如请求/响应示例、注意事项等"
          >
            <TextArea
              rows={6}
              placeholder='{\n  "request_example": {...},\n  "response_example": {...},\n  "notes": "需要携带 Token"\n}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select
              mode="tags"
              placeholder="输入标签，按回车添加"
              style={{ width: '100%' }}
              tokenSeparators={[',', ' ']}
            />
          </Form.Item>
          <Form.Item name="project_id" label="项目 ID（可选）">
            <Input placeholder="关联项目 ID，留空表示全局" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
