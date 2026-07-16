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
  Descriptions,
  Badge,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { scheduledTaskApi, testCaseApi, projectApi } from '../services/api';
import type { TestCase, Project } from '../types';

const { TextArea } = Input;

const resultBadge: Record<string, string> = {
  success: '#52c41a',
  passed: '#52c41a',
  failed: '#ff4d4f',
  error: '#faad14',
  running: '#1677ff',
};

const resultLabel: Record<string, string> = {
  success: '成功',
  passed: '通过',
  failed: '失败',
  error: '错误',
  running: '执行中',
};

export default function ScheduledTasksPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [cases, setCases] = useState<TestCase[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 立即执行结果
  const [runResult, setRunResult] = useState<any>(null);
  const [runResultOpen, setRunResultOpen] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await scheduledTaskApi.list({ page: p, page_size: ps });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadCases() {
    try {
      const res = await testCaseApi.list({ page: 1, page_size: 100 });
      setCases(res.data || []);
    } catch (e: any) {
      message.error(e.message);
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
    loadCases();
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const projectNameMap = new Map<string, Project>();
  projects.forEach((p) => projectNameMap.set(p.id, p));

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ mode: 'interval', is_enabled: true, case_ids: [] });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      mode: record.mode || 'interval',
      schedule_config: record.schedule_config,
      case_ids: record.case_ids || record.test_case_ids || [],
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
      const payload: any = {
        name: values.name,
        mode: values.mode,
        schedule_config: values.schedule_config,
        case_ids: values.case_ids || [],
        project_id: values.project_id || null,
        is_enabled: values.is_enabled ?? true,
        description: values.description,
      };
      if (editing) {
        await scheduledTaskApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await scheduledTaskApi.create(payload);
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
      await scheduledTaskApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleToggle(record: any) {
    try {
      await scheduledTaskApi.toggle(record.id);
      message.success(record.is_enabled ? '已禁用' : '已启用');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleRun(record: any) {
    setRunningId(record.id);
    try {
      const res = await scheduledTaskApi.run(record.id);
      setRunResult(res.data);
      setRunResultOpen(true);
      message.success('执行已触发');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRunningId(null);
    }
  }

  function scheduleText(record: any): string {
    const mode = record.mode || 'interval';
    const cfg = record.schedule_config;
    if (mode === 'interval') {
      return `每 ${cfg} 秒`;
    }
    return `Cron: ${cfg}`;
  }

  const columns = [
    { title: '名称', dataIndex: 'name', width: 160, ellipsis: true },
    {
      title: '模式',
      dataIndex: 'mode',
      width: 100,
      render: (m: string) => (
        <Tag color={m === 'cron' ? 'purple' : 'blue'}>
          {m === 'cron' ? 'Cron 表达式' : '固定间隔'}
        </Tag>
      ),
    },
    {
      title: '调度配置',
      width: 180,
      render: (_: any, record: any) => (
        <Tooltip title={record.schedule_config}>
          <span>{scheduleText(record)}</span>
        </Tooltip>
      ),
    },
    {
      title: '用例数',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: any) =>
        (record.case_ids || record.test_case_ids || []).length,
    },
    {
      title: '状态',
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
      title: '上次执行时间',
      width: 170,
      render: (_: any, record: any) => {
        const t = record.last_run_at || record.last_executed_at;
        return t ? new Date(t).toLocaleString('zh-CN') : '-';
      },
    },
    {
      title: '上次结果',
      width: 100,
      render: (_: any, record: any) => {
        const r = record.last_result || record.last_run_result;
        if (!r) return '-';
        return (
          <Badge
            color={resultBadge[r] || '#d9d9d9'}
            text={resultLabel[r] || r}
          />
        );
      },
    },
    {
      title: '操作',
      width: 240,
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<PlayCircleOutlined />}
            loading={runningId === record.id}
            onClick={() => handleRun(record)}
          >
            立即执行
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除该任务？"
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

  const mode = Form.useWatch('mode', form);

  return (
    <div>
      <Card
        title={
          <Space>
            <ClockCircleOutlined />
            <span>定时任务</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个任务
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建任务
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
          locale={{ emptyText: <Empty description="暂无定时任务" /> }}
        />
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑定时任务' : '新建定时任务'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ mode: 'interval', is_enabled: true }}>
          <Form.Item
            name="name"
            label="任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="如：每日冒烟测试" />
          </Form.Item>

          <Form.Item
            name="mode"
            label="调度模式"
            rules={[{ required: true, message: '请选择调度模式' }]}
          >
            <Select
              options={[
                { value: 'interval', label: '固定间隔（interval）' },
                { value: 'cron', label: 'Cron 表达式（cron）' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="schedule_config"
            label="调度配置"
            rules={[{ required: true, message: '请输入调度配置' }]}
            extra={
              mode === 'cron' ? (
                <span style={{ color: '#6b7280' }}>
                  Cron 表达式，如 <code>0 2 * * *</code> 表示每天 2 点执行
                </span>
              ) : (
                <span style={{ color: '#6b7280' }}>
                  间隔秒数，如 <code>300</code> 表示每 5 分钟执行一次
                </span>
              )
            }
          >
            <Input
              placeholder={mode === 'cron' ? '0 2 * * *' : '300'}
            />
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

          <Form.Item
            name="case_ids"
            label="执行用例"
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

          <Form.Item name="is_enabled" label="是否启用">
            <Select
              options={[
                { value: true, label: '启用' },
                { value: false, label: '禁用' },
              ]}
            />
          </Form.Item>

          <Form.Item name="description" label="任务描述">
            <TextArea rows={2} placeholder="任务描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 立即执行结果 Modal */}
      <Modal
        title="执行结果"
        open={runResultOpen}
        onCancel={() => setRunResultOpen(false)}
        footer={
          <Button type="primary" onClick={() => setRunResultOpen(false)}>
            关闭
          </Button>
        }
        width={640}
      >
        {runResult && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="执行状态">
                <Badge
                  color={resultBadge[runResult.status] || '#d9d9d9'}
                  text={resultLabel[runResult.status] || runResult.status || '-'}
                />
              </Descriptions.Item>
              <Descriptions.Item label="Run ID">
                {runResult.run_id || runResult.id || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="总数">
                {runResult.total ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="通过">
                <span style={{ color: '#52c41a' }}>{runResult.passed ?? '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="失败">
                <span style={{ color: '#ff4d4f' }}>{runResult.failed ?? '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="错误">
                <span style={{ color: '#faad14' }}>{runResult.error ?? '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="耗时" span={2}>
                {runResult.duration != null ? `${runResult.duration}s` : '-'}
              </Descriptions.Item>
            </Descriptions>
            {runResult.message && (
              <div style={{ marginTop: 12, color: '#6b7280' }}>
                {runResult.message}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
