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
  Tag,
  Card,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  ReloadOutlined,
  BugOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import type { ApiResponse, PageResponse } from '../types';
import { apiClient } from '../services/api';
import dayjs from 'dayjs';

const { TextArea } = Input;

interface DefectTicket {
  id: string;
  external_id: string | null;
  external_system: string | null;
  title: string;
  description: string | null;
  status: string;
  severity: string;
  project_id: string | null;
  test_result_id: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

const STATUS_OPTIONS = [
  { label: '待处理', value: 'open' },
  { label: '处理中', value: 'in_progress' },
  { label: '已解决', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
];

const STATUS_COLOR: Record<string, string> = {
  open: 'default',
  in_progress: 'processing',
  resolved: 'success',
  closed: 'blue',
};

const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
};

const SEVERITY_OPTIONS = [
  { label: '致命 (critical)', value: 'critical' },
  { label: '高 (high)', value: 'high' },
  { label: '中 (normal)', value: 'normal' },
  { label: '低 (low)', value: 'low' },
];

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'volcano',
  normal: 'orange',
  low: 'blue',
};

const EXTERNAL_SYSTEM_OPTIONS = [
  { label: 'Jira', value: 'jira' },
  { label: '禅道', value: 'zentao' },
  { label: 'GitLab', value: 'gitlab' },
  { label: 'Azure DevOps', value: 'azure_devops' },
];

const EXTERNAL_SYSTEM_LABEL: Record<string, string> = {
  jira: 'Jira',
  zentao: '禅道',
  gitlab: 'GitLab',
  azure_devops: 'Azure DevOps',
};

export default function DefectsPage() {
  const [data, setData] = useState<DefectTicket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [severityFilter, setSeverityFilter] = useState<string | undefined>(
    undefined
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DefectTicket | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const [syncing, setSyncing] = useState<string | null>(null);

  async function loadData(
    p = page,
    ps = pageSize,
    st = statusFilter,
    sv = severityFilter
  ) {
    setLoading(true);
    try {
      const params: Record<string, any> = { page: p, page_size: ps };
      if (st) params.status = st;
      if (sv) params.severity = sv;
      const res = await apiClient.get<unknown, PageResponse<DefectTicket>>(
        '/defects',
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      status: 'open',
      severity: 'normal',
    });
    setModalOpen(true);
  }

  function openEdit(record: DefectTicket) {
    setEditing(record);
    form.setFieldsValue({
      title: record.title,
      description: record.description,
      status: record.status,
      severity: record.severity,
      external_system: record.external_system,
      external_id: record.external_id,
      project_id: record.project_id,
      test_result_id: record.test_result_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (editing) {
        await apiClient.put<unknown, ApiResponse<DefectTicket>>(
          `/defects/${editing.id}`,
          values
        );
        message.success('更新成功');
      } else {
        await apiClient.post<unknown, ApiResponse<DefectTicket>>(
          '/defects',
          values
        );
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

  async function handleSync(record: DefectTicket) {
    setSyncing(record.id);
    try {
      const res = await apiClient.post<
        unknown,
        ApiResponse<{ synced: boolean; message: string }>
      >(`/defects/${record.id}/sync`);
      if (res.data.synced) {
        message.success(res.data.message);
      } else {
        message.warning(res.data.message);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSyncing(null);
    }
  }

  return (
    <div data-testid="defects-page">
      <Card
        title={
          <Space>
            <BugOutlined />
            <span>缺陷管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条
            </span>
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 130 }}
              options={STATUS_OPTIONS}
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                setPage(1);
                loadData(1, pageSize, v, severityFilter);
              }}
            />
            <Select
              allowClear
              placeholder="严重程度"
              style={{ width: 150 }}
              options={SEVERITY_OPTIONS}
              value={severityFilter}
              onChange={(v) => {
                setSeverityFilter(v);
                setPage(1);
                loadData(1, pageSize, statusFilter, v);
              }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建缺陷
            </Button>
          </Space>
        }
      >
        <Table
          data-testid="defects-table"
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
          scroll={{ x: 1200 }}
          columns={[
            {
              title: '标题',
              dataIndex: 'title',
              ellipsis: true,
              render: (v: string) => (
                <Tooltip title={v}>
                  <span style={{ fontWeight: 600 }}>{v}</span>
                </Tooltip>
              ),
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (v: string) => (
                <Tag color={STATUS_COLOR[v] || 'default'}>
                  {STATUS_LABEL[v] || v}
                </Tag>
              ),
            },
            {
              title: '严重程度',
              dataIndex: 'severity',
              width: 110,
              render: (v: string) => (
                <Tag color={SEVERITY_COLOR[v] || 'default'}>{v}</Tag>
              ),
            },
            {
              title: '外部系统',
              width: 130,
              render: (_, r) =>
                r.external_system ? (
                  <Tag>
                    {EXTERNAL_SYSTEM_LABEL[r.external_system] || r.external_system}
                    {r.external_id ? `: ${r.external_id}` : ''}
                  </Tag>
                ) : (
                  '-'
                ),
            },
            {
              title: '关联测试结果',
              dataIndex: 'test_result_id',
              width: 160,
              ellipsis: true,
              render: (v: string | null) => v || '-',
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 170,
              render: (t: string | null) =>
                t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
            },
            {
              title: '操作',
              width: 180,
              fixed: 'right',
              render: (_, record) => (
                <Space>
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => openEdit(record)}
                  >
                    编辑
                  </Button>
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    loading={syncing === record.id}
                    onClick={() => handleSync(record)}
                  >
                    同步
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? '编辑缺陷' : '新建缺陷'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="缺陷标题"
            rules={[{ required: !editing, message: '请输入缺陷标题（或填写测试结果 ID 自动生成）' }]}
          >
            <Input placeholder="留空且提供测试结果 ID 时将自动生成" />
          </Form.Item>
          <Form.Item name="test_result_id" label="关联测试结果 ID（可选）">
            <Input placeholder="从失败测试结果创建缺陷时填写" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="缺陷描述（可选）" />
          </Form.Item>
          <Space style={{ display: 'flex' }} size="middle">
            <Form.Item name="status" label="状态" style={{ flex: 1, minWidth: 150 }}>
              <Select options={STATUS_OPTIONS} />
            </Form.Item>
            <Form.Item name="severity" label="严重程度" style={{ flex: 1, minWidth: 170 }}>
              <Select options={SEVERITY_OPTIONS} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} size="middle">
            <Form.Item name="external_system" label="外部系统" style={{ flex: 1, minWidth: 170 }}>
              <Select
                allowClear
                options={EXTERNAL_SYSTEM_OPTIONS}
                placeholder="可选"
              />
            </Form.Item>
            <Form.Item name="external_id" label="外部 ID" style={{ flex: 1, minWidth: 170 }}>
              <Input placeholder="可选" />
            </Form.Item>
          </Space>
          <Form.Item name="project_id" label="项目 ID（可选）">
            <Input placeholder="关联项目 ID" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
