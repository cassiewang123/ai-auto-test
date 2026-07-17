import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Select,
  Space,
  message,
  Card,
  Statistic,
  Row,
  Col,
  Tag,
  Modal,
  Form,
  Input,
  Rate,
} from 'antd';
import {
  ReloadOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  RobotOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import type { ApiResponse, PageResponse } from '../types';
import { apiClient } from '../services/api';
import dayjs from 'dayjs';

interface AIInvocation {
  id: string;
  model: string | null;
  provider: string | null;
  prompt_version: string | null;
  input_hash: string | null;
  token_usage_input: number;
  token_usage_output: number;
  token_usage_total: number;
  latency_ms: number | null;
  cost: number;
  output_schema_valid: boolean | null;
  accepted: boolean | null;
  edited: boolean | null;
  rejected: boolean | null;
  feedback_comment: string | null;
  invoked_by: string | null;
  created_at: string | null;
}

interface AIStats {
  total_invocations: number;
  total_cost: number;
  total_tokens: number;
  accepted: number;
  rejected: number;
  acceptance_rate: number;
}

const PROVIDER_OPTIONS = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'GLM', value: 'glm' },
];

function feedbackTag(inv: AIInvocation) {
  if (inv.accepted) return <Tag color="green">已采纳</Tag>;
  if (inv.edited) return <Tag color="orange">修改后采纳</Tag>;
  if (inv.rejected) return <Tag color="red">已拒绝</Tag>;
  return <Tag>未反馈</Tag>;
}

export default function AiOpsPage() {
  const [data, setData] = useState<AIInvocation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [provider, setProvider] = useState<string | undefined>(undefined);
  const [stats, setStats] = useState<AIStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [editing, setEditing] = useState<AIInvocation | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  async function loadStats() {
    setStatsLoading(true);
    try {
      const res = await apiClient.get<unknown, ApiResponse<AIStats>>(
        '/ai-ops/stats'
      );
      setStats(res.data);
    } catch (e: any) {
      // 静默失败，统计卡片非关键路径
    } finally {
      setStatsLoading(false);
    }
  }

  async function loadData(p = page, ps = pageSize, prov = provider) {
    setLoading(true);
    try {
      const params: Record<string, any> = { page: p, page_size: ps };
      if (prov) params.provider = prov;
      const res = await apiClient.get<unknown, PageResponse<AIInvocation>>(
        '/ai-ops/invocations',
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
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openFeedback(record: AIInvocation) {
    setEditing(record);
    form.resetFields();
    form.setFieldsValue({ rating: 0, comment: '' });
    setFeedbackOpen(true);
  }

  async function handleSubmitFeedback() {
    if (!editing) return;
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      // 根据用户选择的反馈类型提交
      const payload: Record<string, any> = {};
      if (values.feedback_type === 'accepted') payload.accepted = true;
      else if (values.feedback_type === 'edited') payload.edited = true;
      else if (values.feedback_type === 'rejected') payload.rejected = true;
      if (values.comment) payload.comment = values.comment;
      if (values.rating) payload.rating = values.rating;
      await apiClient.post(`/ai-ops/invocations/${editing.id}/feedback`, payload);
      message.success('反馈已提交');
      setFeedbackOpen(false);
      loadData();
      loadStats();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div data-testid="ai-ops-page">
      <div data-testid="ai-stats-cards" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col xs={24} sm={12} lg={6}>
            <Card loading={statsLoading}>
              <Statistic
                title="调用次数"
                value={stats?.total_invocations ?? 0}
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card loading={statsLoading}>
              <Statistic
                title="总成本 (USD)"
                value={stats?.total_cost ?? 0}
                precision={4}
                prefix={<DollarOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card loading={statsLoading}>
              <Statistic
                title="Token 用量"
                value={stats?.total_tokens ?? 0}
                prefix={<RobotOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card loading={statsLoading}>
              <Statistic
                title="采纳率 (%)"
                value={stats?.acceptance_rate ?? 0}
                precision={1}
                prefix={<CheckCircleOutlined />}
                styles={{ content: { color: '#059669' } }}
              />
            </Card>
          </Col>
        </Row>
      </div>

      <Card
        title={
          <Space>
            <span>AI 调用记录</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条
            </span>
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              allowClear
              placeholder="供应商"
              style={{ width: 150 }}
              options={PROVIDER_OPTIONS}
              value={provider}
              onChange={(v) => {
                setProvider(v);
                setPage(1);
                loadData(1, pageSize, v);
              }}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                loadData();
                loadStats();
              }}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          data-testid="ai-invocations-table"
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
          scroll={{ x: 1100 }}
          columns={[
            {
              title: '模型',
              dataIndex: 'model',
              width: 140,
              render: (v: string | null) => v || '-',
            },
            {
              title: '供应商',
              dataIndex: 'provider',
              width: 110,
              render: (v: string | null) => v || '-',
            },
            {
              title: '输入哈希',
              dataIndex: 'input_hash',
              width: 130,
              render: (v: string | null) => (
                <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
                  {v || '-'}
                </span>
              ),
            },
            {
              title: 'Token (入/出)',
              width: 140,
              render: (_, r) => `${r.token_usage_input} / ${r.token_usage_output}`,
            },
            {
              title: '延迟 (ms)',
              dataIndex: 'latency_ms',
              width: 100,
              render: (v: number | null) => v ?? '-',
            },
            {
              title: '成本',
              dataIndex: 'cost',
              width: 90,
              render: (v: number) => `$${Number(v || 0).toFixed(4)}`,
            },
            {
              title: '反馈',
              width: 120,
              render: (_, r) => feedbackTag(r),
            },
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 170,
              render: (t: string | null) =>
                t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
            },
            {
              title: '操作',
              width: 100,
              fixed: 'right',
              render: (_, record) => (
                <Button size="small" onClick={() => openFeedback(record)}>
                  反馈
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="提交 AI 调用反馈"
        open={feedbackOpen}
        onOk={handleSubmitFeedback}
        confirmLoading={submitting}
        onCancel={() => setFeedbackOpen(false)}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="feedback_type" label="反馈类型">
            <Select
              placeholder="选择反馈类型"
              options={[
                { label: '采纳', value: 'accepted' },
                { label: '修改后采纳', value: 'edited' },
                { label: '拒绝', value: 'rejected' },
              ]}
            />
          </Form.Item>
          <Form.Item name="rating" label="评分">
            <Rate />
          </Form.Item>
          <Form.Item name="comment" label="评论">
            <Input.TextArea rows={3} placeholder="可选：填写反馈评论" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
