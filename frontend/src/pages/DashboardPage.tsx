import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ApiOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  environmentApi,
  jobsApi,
  reportApi,
  testCaseApi,
  testPlanApi,
} from '../services/api';
import type { Job, JobStatus, JobType, TestCase } from '../types';

const { Text, Title } = Typography;

interface ReportRun {
  total?: number;
  passed?: number;
}

interface DashboardLoadError {
  source: string;
  message: string;
}

const jobStatusMeta: Record<JobStatus, { color: string; label: string }> = {
  queued: { color: 'blue', label: '排队中' },
  running: { color: 'processing', label: '运行中' },
  succeeded: { color: 'green', label: '成功' },
  failed: { color: 'red', label: '失败' },
  cancelled: { color: 'orange', label: '已取消' },
  timed_out: { color: 'volcano', label: '已超时' },
};

const jobTypeLabels: Record<JobType, string> = {
  api_case: 'API 用例',
  ui_case: 'UI 用例',
  ui_suite: 'UI 套件',
  performance: '性能测试',
};

const methodColors: Record<string, string> = {
  GET: 'green',
  POST: 'orange',
  PUT: 'blue',
  PATCH: 'purple',
  DELETE: 'red',
};

function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN');
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error && reason.message ? reason.message : '请求失败';
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [errors, setErrors] = useState<DashboardLoadError[]>([]);
  const [envCount, setEnvCount] = useState(0);
  const [caseCount, setCaseCount] = useState(0);
  const [planCount, setPlanCount] = useState(0);
  const [recentCases, setRecentCases] = useState<TestCase[]>([]);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [recentRuns, setRecentRuns] = useState<ReportRun[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);

    const results = await Promise.allSettled([
      environmentApi.list({ page: 1, page_size: 1 }),
      testCaseApi.list({ page: 1, page_size: 6 }),
      testPlanApi.list({ page: 1, page_size: 1 }),
      jobsApi.list({ page: 1, page_size: 6 }),
      reportApi.listRuns(10),
    ]);

    const [environmentResult, caseResult, planResult, jobResult, reportResult] = results;
    const nextErrors: DashboardLoadError[] = [];

    if (environmentResult.status === 'fulfilled') {
      setEnvCount(environmentResult.value.total || 0);
    } else {
      nextErrors.push({
        source: '环境数据',
        message: errorMessage(environmentResult.reason),
      });
    }

    if (caseResult.status === 'fulfilled') {
      setCaseCount(caseResult.value.total || 0);
      setRecentCases(caseResult.value.data || []);
    } else {
      nextErrors.push({
        source: 'API 用例',
        message: errorMessage(caseResult.reason),
      });
    }

    if (planResult.status === 'fulfilled') {
      setPlanCount(planResult.value.total || 0);
    } else {
      nextErrors.push({
        source: '测试计划',
        message: errorMessage(planResult.reason),
      });
    }

    if (jobResult.status === 'fulfilled') {
      setRecentJobs(jobResult.value.data || []);
    } else {
      nextErrors.push({
        source: '执行任务',
        message: errorMessage(jobResult.reason),
      });
    }

    if (reportResult.status === 'fulfilled') {
      setRecentRuns(reportResult.value.data || []);
    } else {
      nextErrors.push({
        source: '执行报告',
        message: errorMessage(reportResult.reason),
      });
    }

    setErrors(nextErrors);
    setInitialized(true);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const recentPassRate = useMemo(() => {
    const totals = recentRuns.reduce<{ total: number; passed: number }>(
      (summary, run) => ({
        total: summary.total + (Number(run.total) || 0),
        passed: summary.passed + (Number(run.passed) || 0),
      }),
      { total: 0, passed: 0 }
    );
    return totals.total > 0 ? (totals.passed / totals.total) * 100 : 0;
  }, [recentRuns]);

  const jobColumns: ColumnsType<Job> = [
    {
      title: '类型',
      dataIndex: 'job_type',
      width: 100,
      render: (jobType: JobType) => jobTypeLabels[jobType],
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 88,
      render: (status: JobStatus) => {
        const meta = jobStatusMeta[status];
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: '结果',
      key: 'result',
      ellipsis: true,
      render: (_, job) =>
        job.result_summary || job.error_message || (job.status === 'queued' ? '等待执行' : '-'),
    },
    {
      title: '时间',
      key: 'time',
      width: 168,
      render: (_, job) =>
        formatDateTime(job.finished_at || job.started_at || job.created_at || job.queued_at),
    },
  ];

  const caseColumns: ColumnsType<TestCase> = [
    {
      title: '方法',
      dataIndex: 'method',
      width: 82,
      render: (method: string) => (
        <Tag color={methodColors[method] || 'default'}>{method}</Tag>
      ),
    },
    {
      title: '名称',
      dataIndex: 'title',
      ellipsis: true,
    },
    {
      title: '接口地址',
      dataIndex: 'url',
      ellipsis: true,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 168,
      render: (value: string) => formatDateTime(value),
    },
  ];

  if (!initialized) {
    return (
      <div style={{ padding: 80, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div
        style={{
          alignItems: 'flex-start',
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          justifyContent: 'space-between',
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0 }}>
            个人测试工作台
          </Title>
          <Text type="secondary">集中查看本机测试资产和最近执行状态</Text>
        </div>
        <Space wrap data-testid="quick-actions">
          <Button icon={<PlayCircleOutlined />} onClick={() => navigate('/quick-test')}>
            接口调试
          </Button>
          <Button icon={<UnorderedListOutlined />} onClick={() => navigate('/api-list')}>
            接口列表
          </Button>
          <Button icon={<CalendarOutlined />} onClick={() => navigate('/jobs')}>
            任务中心
          </Button>
          <Button icon={<FileTextOutlined />} onClick={() => navigate('/reports')}>
            报告
          </Button>
          <Button
            aria-label="刷新工作台"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void loadData()}
          />
        </Space>
      </div>

      {errors.length > 0 && (
        <Alert
          data-testid="dashboard-error"
          type="warning"
          showIcon
          title="部分工作台数据加载失败"
          description={errors.map((error) => `${error.source}：${error.message}`).join('；')}
          action={
            <Button size="small" loading={loading} onClick={() => void loadData()}>
              重试
            </Button>
          }
        />
      )}

      <Row gutter={[12, 12]} data-testid="stats-cards">
        <Col xs={12} lg={6}>
          <Card size="small" style={{ borderRadius: 6 }}>
            <Statistic
              title="API 用例"
              value={caseCount}
              prefix={<ApiOutlined />}
              styles={{ content: { color: '#2563eb' } }}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" style={{ borderRadius: 6 }}>
            <Statistic
              title="测试环境"
              value={envCount}
              prefix={<CloudServerOutlined />}
              styles={{ content: { color: '#0f766e' } }}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" style={{ borderRadius: 6 }}>
            <Statistic
              title="测试计划"
              value={planCount}
              prefix={<CalendarOutlined />}
              styles={{ content: { color: '#a16207' } }}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" style={{ borderRadius: 6 }}>
            <Statistic
              title="近期通过率"
              value={recentPassRate}
              precision={1}
              suffix="%"
              prefix={<CheckCircleOutlined />}
              styles={{ content: { color: '#15803d' } }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title="最近执行任务"
        data-testid="recent-jobs"
        style={{ borderRadius: 6 }}
        extra={
          <Button type="link" size="small" onClick={() => navigate('/jobs')}>
            全部任务
          </Button>
        }
      >
        {recentJobs.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行任务" />
        ) : (
          <Table
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={recentJobs}
            columns={jobColumns}
            pagination={false}
            scroll={{ x: 720 }}
          />
        )}
      </Card>

      <Card
        size="small"
        title="最近 API 用例"
        data-testid="recent-cases"
        style={{ borderRadius: 6 }}
        extra={
          <Button type="link" size="small" onClick={() => navigate('/api-list')}>
            全部接口
          </Button>
        }
      >
        {recentCases.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 API 用例" />
        ) : (
          <Table
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={recentCases}
            columns={caseColumns}
            pagination={false}
            scroll={{ x: 760 }}
          />
        )}
      </Card>
    </div>
  );
}
