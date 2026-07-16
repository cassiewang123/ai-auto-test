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
  Badge,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ProjectOutlined,
} from '@ant-design/icons';
import { projectApi } from '../services/api';
import type { Project, ProjectCreate } from '../types';
import { useNavigate } from 'react-router-dom';

const { TextArea } = Input;

// 兼容后端 stats 返回的不同字段名
function extractCount(d: any): number {
  if (!d) return 0;
  if (typeof d.total === 'number') return d.total;
  if (typeof d.test_cases === 'number') return d.test_cases;
  if (typeof d.case_count === 'number') return d.case_count;
  return 0;
}

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [statsMap, setStatsMap] = useState<Record<string, number>>({});
  const [searchName, setSearchName] = useState('');
  const [form] = Form.useForm<ProjectCreate>();

  async function loadData() {
    setLoading(true);
    try {
      const res = await projectApi.listAll();
      const list = res.data || [];
      setData(list);
      // 并发加载每个项目的统计信息
      const stats: Record<string, number> = {};
      await Promise.all(
        list.map(async (p) => {
          try {
            const s = await projectApi.stats(p.id);
            stats[p.id] = extractCount(s.data);
          } catch {
            stats[p.id] = 0;
          }
        })
      );
      setStatsMap(stats);
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
    setModalOpen(true);
  }

  function openEdit(record: Project) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      code: record.code,
      base_url: record.base_url,
      description: record.description,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      const payload: ProjectCreate = {
        name: values.name,
        code: values.code,
        base_url: values.base_url,
        description: values.description,
      };
      setSubmitting(true);
      if (editing) {
        await projectApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await projectApi.create(payload);
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
      await projectApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const filtered = data.filter((p) => {
    if (!searchName) return true;
    const s = searchName.toLowerCase();
    return (
      p.name.toLowerCase().includes(s) ||
      (p.code || '').toLowerCase().includes(s) ||
      (p.description || '').toLowerCase().includes(s)
    );
  });

  return (
    <div>
      <Card
        title={
          <Space>
            <ProjectOutlined />
            <span>项目管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {data.length} 个项目
            </span>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索项目名称、标识、描述"
              allowClear
              style={{ width: 260 }}
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
            />
            <Button icon={<ReloadOutlined />} onClick={loadData}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-testid="create-project-btn">
              新建项目
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={filtered}
          rowKey="id"
          loading={loading}
          data-testid="projects-table"
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
          columns={[
            {
              title: '名称',
              dataIndex: 'name',
              width: 180,
              render: (v: string, record: Project) => (
                <Space>
                  <ProjectOutlined style={{ color: '#2563eb' }} />
                  <a
                    style={{ fontWeight: 600, cursor: 'pointer' }}
                    onClick={() => navigate(`/api-list?project_id=${record.id}`)}
                  >
                    {v}
                  </a>
                </Space>
              ),
            },
            { title: '描述', dataIndex: 'description', ellipsis: true,
              render: (v: string) => v || '-' },
            {
              title: 'Base URL',
              dataIndex: 'base_url',
              ellipsis: true,
              render: (v: string) => v || '-',
            },
            {
              title: '项目标识',
              dataIndex: 'code',
              width: 140,
              render: (v: string) => (v ? <Tag color="blue">{v}</Tag> : '-'),
            },
            {
              title: '接口数量',
              width: 110,
              render: (_, record) => (
                <a
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/api-list?project_id=${record.id}`)}
                >
                  <Badge
                    count={statsMap[record.id] ?? 0}
                    style={{ backgroundColor: '#e5e7eb', color: '#374151' }}
                    overflowCount={9999}
                  />
                </a>
              ),
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 180,
              render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
            },
            {
              title: '操作',
              width: 240,
              render: (_, record) => (
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    ghost
                    onClick={() => navigate(`/api-list?project_id=${record.id}`)}
                  >
                    查看接口
                  </Button>
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => openEdit(record)}
                  >
                    编辑
                  </Button>
                  <Popconfirm
                    title="确认删除该项目？"
                    description="删除后项目下的接口将变为未分类。"
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
        title={editing ? '编辑项目' : '新建项目'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={560}
        destroyOnClose
        data-testid={editing ? 'edit-modal' : 'create-modal'}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="如：用户中心" />
          </Form.Item>
          <Form.Item name="code" label="项目标识">
            <Input placeholder="如：user-center（可选）" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="如：http://robin.ep.local:30080" />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <TextArea rows={3} placeholder="项目描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
