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
  Empty,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CopyOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { uiElementApi, projectApi } from '../services/api';
import type { Project } from '../types';

const { TextArea } = Input;

const selectorTypeColor: Record<string, string> = {
  css: 'blue',
  xpath: 'purple',
  id: 'green',
  name: 'orange',
};

const SELECTOR_TYPES = ['css', 'xpath', 'id', 'name'];

// 复制文本到剪贴板，带降级处理
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(textarea);
      return ok;
    } catch {
      return false;
    }
  }
}

export default function UiElementsPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [projects, setProjects] = useState<Project[]>([]);
  const [filterProject, setFilterProject] = useState<string | undefined>(undefined);
  const [nameSearch, setNameSearch] = useState('');

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  async function loadData(
    p = page,
    ps = pageSize,
    projectId = filterProject,
    name = nameSearch
  ) {
    setLoading(true);
    try {
      const res = await uiElementApi.list({
        page: p,
        page_size: ps,
        project_id: projectId,
        name_search: name,
      });
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
    form.setFieldsValue({ selector_type: 'css' });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      selector_type: record.selector_type,
      selector_value: record.selector_value,
      page_url: record.page_url,
      description: record.description,
      project_id: record.project_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload: any = {
        name: values.name,
        selector_type: values.selector_type,
        selector_value: values.selector_value,
        page_url: values.page_url || null,
        description: values.description,
        project_id: values.project_id || null,
      };
      if (editing) {
        await uiElementApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await uiElementApi.create(payload);
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
      await uiElementApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleCopy(value: string) {
    const ok = await copyToClipboard(value);
    if (ok) {
      message.success('已复制选择器值');
    } else {
      message.error('复制失败，请手动复制');
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name', width: 160, ellipsis: true },
    {
      title: '选择器类型',
      dataIndex: 'selector_type',
      width: 110,
      render: (t: string) => (
        <Tag color={selectorTypeColor[t] || 'default'}>{t || '-'}</Tag>
      ),
    },
    {
      title: '选择器值',
      dataIndex: 'selector_value',
      width: 280,
      render: (v: string, record: any) =>
        v ? (
          <Tooltip title="点击复制">
            <code
              style={{
                cursor: 'pointer',
                background: '#f5f5f5',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 12,
                color: '#2563eb',
                display: 'inline-block',
                maxWidth: 240,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                verticalAlign: 'middle',
              }}
              onClick={() => handleCopy(record.selector_value)}
            >
              {v}
            </code>
            <Button
              size="small"
              type="link"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(record.selector_value)}
            />
          </Tooltip>
        ) : (
          '-'
        ),
    },
    {
      title: '页面 URL',
      dataIndex: 'page_url',
      width: 200,
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
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
            title="确认删除该元素？"
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
            <ApartmentOutlined />
            <span>元素对象库</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个元素
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建元素
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} size="middle">
          <Select
            allowClear
            placeholder="选择项目"
            style={{ width: 220 }}
            showSearch
            optionFilterProp="label"
            value={filterProject}
            options={projects.map((p) => ({ label: p.name, value: p.id }))}
            onChange={(v) => {
              setFilterProject(v);
              setPage(1);
              loadData(1, pageSize, v, nameSearch);
            }}
          />
          <Input.Search
            placeholder="搜索元素名称"
            allowClear
            style={{ width: 240 }}
            onSearch={(v) => {
              setNameSearch(v);
              setPage(1);
              loadData(1, pageSize, filterProject, v);
            }}
          />
        </Space>

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
          locale={{ emptyText: <Empty description="暂无元素对象" /> }}
        />
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑元素' : '新建元素'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={{ selector_type: 'css' }}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：用户名输入框" />
          </Form.Item>

          <Form.Item
            name="selector_type"
            label="选择器类型"
            rules={[{ required: true, message: '请选择选择器类型' }]}
          >
            <Select
              options={SELECTOR_TYPES.map((t) => ({ label: t, value: t }))}
            />
          </Form.Item>

          <Form.Item
            name="selector_value"
            label="选择器值"
            rules={[{ required: true, message: '请输入选择器值' }]}
          >
            <TextArea
              rows={3}
              placeholder='如 #username 或 //button[@class="submit"]'
            />
          </Form.Item>

          <Form.Item name="page_url" label="页面 URL">
            <Input placeholder="https://example.com/login（可选）" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input placeholder="元素描述（可选）" />
          </Form.Item>

          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              showSearch
              optionFilterProp="label"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
