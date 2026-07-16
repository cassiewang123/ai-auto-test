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
  Switch,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import type { ApiResponse, PageResponse } from '../types';
import { apiClient } from '../services/api';
import dayjs from 'dayjs';

const { TextArea } = Input;

interface QualityGate {
  id: string;
  name: string;
  project_id: string | null;
  rules: Array<Record<string, any>> | null;
  mode: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

const MODE_OPTIONS = [
  { label: '阻断 (block)', value: 'block' },
  { label: '告警 (warn)', value: 'warn' },
  { label: '记录 (log)', value: 'log' },
];

const MODE_COLOR: Record<string, string> = {
  block: 'red',
  warn: 'orange',
  log: 'blue',
};

function stringifyRules(rules: any): string {
  if (!rules) return '';
  if (typeof rules === 'string') return rules;
  try {
    return JSON.stringify(rules, null, 2);
  } catch {
    return '';
  }
}

export default function QualityGatesPage() {
  const [data, setData] = useState<QualityGate[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<QualityGate | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await apiClient.get<unknown, PageResponse<QualityGate>>(
        '/quality-gates',
        { params: { page: p, page_size: ps } }
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
    form.setFieldsValue({ mode: 'block', is_active: true, rules: '' });
    setModalOpen(true);
  }

  function openEdit(record: QualityGate) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      project_id: record.project_id,
      mode: record.mode,
      is_active: record.is_active,
      rules: stringifyRules(record.rules),
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      let rules: any = values.rules;
      if (typeof rules === 'string' && rules.trim()) {
        try {
          rules = JSON.parse(rules);
        } catch {
          message.error('门禁规则不是合法的 JSON');
          setSubmitting(false);
          return;
        }
      } else {
        rules = null;
      }
      const payload: any = {
        name: values.name,
        project_id: values.project_id || null,
        mode: values.mode,
        is_active: values.is_active,
        rules,
      };
      if (editing) {
        await apiClient.put<unknown, ApiResponse<QualityGate>>(
          `/quality-gates/${editing.id}`,
          payload
        );
        message.success('更新成功');
      } else {
        await apiClient.post<unknown, ApiResponse<QualityGate>>(
          '/quality-gates',
          payload
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

  async function handleDelete(id: string) {
    try {
      await apiClient.delete<unknown, ApiResponse<any>>(`/quality-gates/${id}`);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  return (
    <div data-testid="quality-gates-page">
      <Card
        title={
          <Space>
            <SafetyOutlined />
            <span>质量门禁</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建门禁
            </Button>
          </Space>
        }
      >
        <Table
          data-testid="quality-gates-table"
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
          columns={[
            {
              title: '门禁名称',
              dataIndex: 'name',
              width: 200,
              render: (v: string) => (
                <span style={{ fontWeight: 600 }}>{v}</span>
              ),
            },
            {
              title: '模式',
              dataIndex: 'mode',
              width: 110,
              render: (v: string) => (
                <Tag color={MODE_COLOR[v] || 'default'}>{v}</Tag>
              ),
            },
            {
              title: '规则数量',
              width: 100,
              render: (_, r) => (r.rules ? r.rules.length : 0),
            },
            {
              title: '项目 ID',
              dataIndex: 'project_id',
              width: 160,
              ellipsis: true,
              render: (v: string | null) => v || '全局',
            },
            {
              title: '状态',
              dataIndex: 'is_active',
              width: 90,
              render: (v: boolean) =>
                v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>,
            },
            {
              title: '更新时间',
              dataIndex: 'updated_at',
              width: 170,
              render: (t: string | null) =>
                t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
            },
            {
              title: '操作',
              width: 160,
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
                    title="确认删除该门禁？"
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
        title={editing ? '编辑质量门禁' : '新建质量门禁'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="门禁名称"
            rules={[{ required: true, message: '请输入门禁名称' }]}
          >
            <Input placeholder="如：发布前质量门禁" />
          </Form.Item>
          <Form.Item
            name="mode"
            label="门禁模式"
            rules={[{ required: true, message: '请选择门禁模式' }]}
          >
            <Select options={MODE_OPTIONS} />
          </Form.Item>
          <Form.Item name="project_id" label="项目 ID（可选）">
            <Input placeholder="留空表示全局门禁" />
          </Form.Item>
          <Form.Item
            name="rules"
            label="门禁规则（JSON 数组）"
            tooltip='如 [{"metric":"pass_rate","op":">=","value":0.9}]'
          >
            <TextArea
              rows={6}
              placeholder='[\n  {"metric": "pass_rate", "op": ">=", "value": 0.9},\n  {"metric": "coverage", "op": ">=", "value": 0.8}\n]'
              style={{ fontFamily: 'monospace' }}
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
