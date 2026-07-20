import { useEffect, useRef, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Row,
  Col,
  Statistic,
  message,
  Empty,
  Modal,
  Spin,
  Tooltip,
  DatePicker,
  Dropdown,
  Select,
  Typography,
} from 'antd';
import {
  ReloadOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FilterOutlined,
  MoreOutlined,
} from '@ant-design/icons';
import { Chart, registerables } from 'chart.js';
import dayjs, { type Dayjs } from 'dayjs';
import { reportApi, reportExportApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';
import '../styles/report-workspace.css';

Chart.register(...registerables);
const { RangePicker } = DatePicker;

// 防御性取值：兼容后端可能返回的不同字段名
function pick(obj: any, keys: string[]): any {
  if (!obj) return undefined;
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  }
  return undefined;
}

const statusColor: Record<string, string> = {
  passed: 'green',
  failed: 'red',
  error: 'orange',
  skipped: 'default',
};

const statusLabel: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  error: '错误',
  skipped: '跳过',
};

function runIdOf(run: any): string {
  return String(pick(run, ['run_id', 'id']) || '');
}

function runSourceOf(run: any): string {
  return String(pick(run, ['source', 'trigger_source', 'trigger', 'job_type']) || '');
}

function runStatusOf(run: any): string {
  return String(pick(run, ['status', 'result', 'job_status']) || '').toLowerCase();
}

function runTimeOf(run: any): number {
  const value = pick(run, ['created_at', 'executed_at', 'run_at', 'time', 'start_time']);
  const timestamp = value ? dayjs(value).valueOf() : Number.NaN;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export default function ReportsPage() {
  const { projects, selectedProjectId, setSelectedProjectId } = useWorkspace();
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string>();
  const [statusFilter, setStatusFilter] = useState<string>();
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [trendFocusRunId, setTrendFocusRunId] = useState<string | null>(null);

  // 详情
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 图表
  const trendCanvasRef = useRef<HTMLCanvasElement>(null);
  const trendChartRef = useRef<Chart | null>(null);
  const pieCanvasRef = useRef<HTMLCanvasElement>(null);
  const pieChartRef = useRef<Chart | null>(null);

  async function loadData(projectId: string | null = selectedProjectId) {
    setLoading(true);
    try {
      const runsRes = await reportApi.listRuns(100, projectId || undefined);
      setRuns(runsRes.data || []);
    } catch (e: any) {
      message.error(e.message);
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData(selectedProjectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  useEffect(() => {
    setSourceFilter(undefined);
    setStatusFilter(undefined);
    setDateRange(null);
    setTrendFocusRunId(null);
  }, [selectedProjectId]);

  const projectScopedRuns = selectedProjectId
    ? runs.filter((run) => String(pick(run, ['project_id'])) === selectedProjectId)
    : runs;
  const sourceOptions = Array.from(
    new Set(projectScopedRuns.map(runSourceOf).filter(Boolean))
  ).sort();
  const statusOptions = Array.from(
    new Set(projectScopedRuns.map(runStatusOf).filter(Boolean))
  ).sort();
  const filteredRuns = projectScopedRuns.filter((run) => {
    if (sourceFilter && runSourceOf(run) !== sourceFilter) return false;
    if (statusFilter && runStatusOf(run) !== statusFilter) return false;
    if (dateRange) {
      const timestamp = runTimeOf(run);
      if (!timestamp) return false;
      const start = dateRange[0].startOf('day').valueOf();
      const end = dateRange[1].endOf('day').valueOf();
      if (timestamp < start || timestamp > end) return false;
    }
    return true;
  });
  const trend = [...filteredRuns].sort((left, right) => runTimeOf(left) - runTimeOf(right)).slice(-10);
  const visibleRuns = trendFocusRunId
    ? filteredRuns.filter((run) => runIdOf(run) === trendFocusRunId)
    : filteredRuns;
  const focusedRun = trendFocusRunId
    ? filteredRuns.find((run) => runIdOf(run) === trendFocusRunId)
    : null;

  function clearFilters() {
    setSourceFilter(undefined);
    setStatusFilter(undefined);
    setDateRange(null);
    setTrendFocusRunId(null);
    if (selectedProjectId) {
      setSelectedProjectId(null);
    } else {
      void loadData(null);
    }
  }

  // 趋势图：混合图表（柱状图：通过/失败数量；折线图：通过率）
  useEffect(() => {
    if (!trendCanvasRef.current) return;

    // 销毁旧实例
    if (trendChartRef.current) {
      trendChartRef.current.destroy();
      trendChartRef.current = null;
    }

    const labels = trend.map((t: any) => {
      const time = pick(t, ['time', 'date', 'run_at', 'executed_at', 'created_at', 'label']);
      if (!time) return '-';
      try {
        return new Date(time).toLocaleString('zh-CN', {
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        });
      } catch {
        return String(time);
      }
    });

    const passedArr = trend.map((t: any) => Number(pick(t, ['passed', 'pass_count'])) || 0);
    const failedArr = trend.map((t: any) =>
      Number(pick(t, ['failed', 'fail_count', 'failure'])) || 0
    );
    const rateArr = trend.map((t: any) => {
      const rate = pick(t, ['pass_rate', 'passing_rate', 'success_rate']);
      if (rate !== undefined) return Number(rate);
      const total = Number(pick(t, ['total'])) || 0;
      const passed = Number(pick(t, ['passed'])) || 0;
      return total > 0 ? (passed / total) * 100 : 0;
    });

    const ctx = trendCanvasRef.current.getContext('2d');
    if (!ctx) return;

    trendChartRef.current = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            type: 'bar',
            label: '通过数',
            data: passedArr,
            backgroundColor: 'rgba(82, 196, 26, 0.6)',
            borderColor: 'rgba(82, 196, 26, 1)',
            borderWidth: 1,
            yAxisID: 'y',
          },
          {
            type: 'bar',
            label: '失败数',
            data: failedArr,
            backgroundColor: 'rgba(255, 77, 79, 0.6)',
            borderColor: 'rgba(255, 77, 79, 1)',
            borderWidth: 1,
            yAxisID: 'y',
          },
          {
            type: 'line',
            label: '通过率(%)',
            data: rateArr,
            borderColor: 'rgba(37, 99, 235, 1)',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            tension: 0.3,
            fill: false,
            yAxisID: 'y1',
            pointRadius: 4,
            pointBackgroundColor: 'rgba(37, 99, 235, 1)',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'top' },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const label = ctx.dataset.label || '';
                const val = ctx.parsed.y;
                if (label.includes('%')) return `${label}: ${Number(val).toFixed(1)}%`;
                return `${label}: ${val}`;
              },
            },
          },
        },
        onClick: (_event, elements) => {
          const element = elements[0];
          const run = element ? trend[element.index] : undefined;
          if (run) {
            setTrendFocusRunId(runIdOf(run));
          }
        },
        scales: {
          x: { title: { display: true, text: '执行时间' } },
          y: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: '用例数量' },
            beginAtZero: true,
          },
          y1: {
            type: 'linear',
            position: 'right',
            title: { display: true, text: '通过率(%)' },
            min: 0,
            max: 100,
            grid: { drawOnChartArea: false },
          },
        },
      },
    });

    return () => {
      if (trendChartRef.current) {
        trendChartRef.current.destroy();
        trendChartRef.current = null;
      }
    };
  }, [trend]);

  // 饼图：通过/失败/错误 占比
  useEffect(() => {
    if (!detailOpen || !detail) return;
    // 等待 canvas 渲染
    const timer = setTimeout(() => {
      if (!pieCanvasRef.current) return;
      if (pieChartRef.current) {
        pieChartRef.current.destroy();
        pieChartRef.current = null;
      }
      const passed = Number(pick(detail, ['passed'])) || 0;
      const failed = Number(pick(detail, ['failed'])) || 0;
      const error = Number(pick(detail, ['error'])) || 0;
      const ctx = pieCanvasRef.current.getContext('2d');
      if (!ctx) return;
      pieChartRef.current = new Chart(ctx, {
        type: 'pie',
        data: {
          labels: ['通过', '失败', '错误'],
          datasets: [
            {
              data: [passed, failed, error],
              backgroundColor: ['#52c41a', '#ff4d4f', '#faad14'],
              borderColor: '#fff',
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'right' },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const total = passed + failed + error;
                  const pct = total > 0 ? ((Number(ctx.parsed) / total) * 100).toFixed(1) : '0';
                  return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
                },
              },
            },
          },
        },
      });
    }, 50);

    return () => {
      clearTimeout(timer);
      if (pieChartRef.current) {
        pieChartRef.current.destroy();
        pieChartRef.current = null;
      }
    };
  }, [detailOpen, detail]);

  // 顶部统计
  const totalRuns = filteredRuns.length;
  const sumTotal = filteredRuns.reduce((s, r) => s + (Number(pick(r, ['total'])) || 0), 0);
  const sumPassed = filteredRuns.reduce((s, r) => s + (Number(pick(r, ['passed'])) || 0), 0);
  const sumDuration = filteredRuns.reduce(
    (s, r) => s + (Number(pick(r, ['duration', 'duration_sum', 'total_duration'])) || 0),
    0
  );
  const overallPassRate = sumTotal > 0 ? (sumPassed / sumTotal) * 100 : 0;
  const avgDuration = totalRuns > 0 ? sumDuration / totalRuns : 0;

  async function openDetail(runId: string) {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      const res = await reportApi.getRunDetail(runId);
      const d = res.data;
      // 后端返回 {summary: {...}, results: [...]}，扁平化以便 pick() 直接取值
      if (d && d.summary) {
        setDetail({ ...d.summary, results: d.results || [] });
      } else {
        setDetail(d);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setDetailLoading(false);
    }
  }

  async function exportReport(runId: string, format: 'html' | 'pdf') {
    try {
      if (format === 'html') {
        await reportExportApi.exportHtml(runId);
      } else {
        await reportExportApi.exportPdf(runId);
      }
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const detailResults: any[] = detail
    ? pick(detail, ['results', 'test_results', 'items']) || []
    : [];

  // 收集数据库断言结果：优先取 run 级 db_results，否则从各用例结果中聚合
  const dbAssertionResults: any[] = (() => {
    if (!detail) return [];
    const runLevel = pick(detail, ['db_results', 'db_assertion_results']);
    if (Array.isArray(runLevel) && runLevel.length > 0) return runLevel;
    // 从每条用例结果中聚合 db_results
    const agg: any[] = [];
    detailResults.forEach((r: any) => {
      const itemResults = pick(r, ['db_results', 'db_assertion_results']);
      if (Array.isArray(itemResults)) {
        const caseTitle = pick(r, ['title', 'test_case_title']);
        itemResults.forEach((item: any) => {
          agg.push({ ...item, case_title: caseTitle });
        });
      }
    });
    return agg;
  })();

  const columns = [
    {
      title: '执行时间',
      width: 170,
      render: (_: any, record: any) => {
        const t = pick(record, ['executed_at', 'created_at', 'run_at', 'time', 'start_time']);
        return t ? new Date(t).toLocaleString('zh-CN') : '-';
      },
    },
    {
      title: '来源',
      width: 110,
      render: (_: any, record: any) => {
        const src = pick(record, ['source', 'trigger_source', 'trigger']);
        return src ? <Tag color="blue">{src}</Tag> : '-';
      },
    },
    {
      title: '总数',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: any) => Number(pick(record, ['total'])) || 0,
    },
    {
      title: '通过',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: any) => (
        <span style={{ color: '#52c41a', fontWeight: 600 }}>
          {Number(pick(record, ['passed'])) || 0}
        </span>
      ),
    },
    {
      title: '失败',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: any) => (
        <span style={{ color: '#ff4d4f', fontWeight: 600 }}>
          {Number(pick(record, ['failed'])) || 0}
        </span>
      ),
    },
    {
      title: '错误',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: any) => (
        <span style={{ color: '#faad14', fontWeight: 600 }}>
          {Number(pick(record, ['error'])) || 0}
        </span>
      ),
    },
    {
      title: '通过率',
      width: 110,
      render: (_: any, record: any) => {
        const total = Number(pick(record, ['total'])) || 0;
        const passed = Number(pick(record, ['passed'])) || 0;
        const rate = pick(record, ['pass_rate', 'passing_rate']);
        const pct = rate !== undefined ? Number(rate) : total > 0 ? (passed / total) * 100 : 0;
        const color = pct >= 80 ? '#52c41a' : pct >= 50 ? '#faad14' : '#ff4d4f';
        return <span style={{ color, fontWeight: 600 }}>{pct.toFixed(1)}%</span>;
      },
    },
    {
      title: '耗时',
      width: 100,
      render: (_: any, record: any) => {
        const d = Number(pick(record, ['duration', 'duration_sum', 'total_duration'])) || 0;
        return `${d.toFixed(2)}s`;
      },
    },
    {
      title: '操作',
      width: 150,
      render: (_: any, record: any) => {
        const runId = runIdOf(record);
        return (
          <Space size="small">
            <Button
              size="small"
              type="link"
              icon={<EyeOutlined />}
              onClick={() => openDetail(runId)}
            >
              详情
            </Button>
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  {
                    key: 'html',
                    label: '导出 HTML',
                    icon: <FileTextOutlined />,
                  },
                  {
                    key: 'pdf',
                    label: '导出 PDF',
                    icon: <DownloadOutlined />,
                  },
                ],
                onClick: ({ key }) => {
                  void exportReport(runId, key as 'html' | 'pdf');
                },
              }}
            >
              <Button
                size="small"
                type="link"
                icon={<MoreOutlined />}
                data-testid="report-export-menu"
              >
                导出
              </Button>
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  const resultColumns = [
    {
      title: '用例标题',
      width: 200,
      ellipsis: true,
      render: (_: any, r: any) =>
        pick(r, ['title', 'test_case_title', 'case_title', 'name']) ||
        pick(r, ['test_case_id', 'case_id']) ||
        '-',
    },
    {
      title: '方法',
      width: 80,
      render: (_: any, r: any) => {
        const m = pick(r, ['method', 'request_method']);
        return m ? <Tag color="blue">{m}</Tag> : '-';
      },
    },
    {
      title: 'URL',
      ellipsis: true,
      render: (_: any, r: any) => {
        const url =
          pick(r, ['url', 'request_url']) ||
          pick(r, ['request', 'url']);
        return url ? <Tooltip title={url}>{url}</Tooltip> : '-';
      },
    },
    {
      title: '状态',
      width: 80,
      render: (_: any, r: any) => {
        const s = pick(r, ['status', 'result']);
        return <Tag color={statusColor[s] || 'default'}>{statusLabel[s] || s || '-'}</Tag>;
      },
    },
    {
      title: '状态码',
      width: 80,
      align: 'center' as const,
      render: (_: any, r: any) => {
        const code =
          pick(r, ['status_code']) || pick(r, ['response', 'status_code']);
        return code != null ? code : '-';
      },
    },
    {
      title: '耗时',
      width: 90,
      render: (_: any, r: any) => {
        const d = Number(pick(r, ['duration', 'elapsed'])) || 0;
        return `${d.toFixed(3)}s`;
      },
    },
    {
      title: '错误',
      ellipsis: true,
      render: (_: any, r: any) => {
        const err = pick(r, ['error_message', 'error', 'message']);
        return err ? <span style={{ color: '#ff4d4f' }}>{err}</span> : '-';
      },
    },
  ];

  // 数据库断言结果列
  const dbResultColumns = [
    {
      title: '断言名称',
      width: 160,
      ellipsis: true,
      render: (_: any, r: any) =>
        pick(r, ['name', 'assertion_name', 'title']) ||
        pick(r, ['assertion_id', 'id']) ||
        '-',
    },
    {
      title: 'SQL',
      ellipsis: true,
      render: (_: any, r: any) => {
        const sql = pick(r, ['sql', 'sql_template', 'executed_sql']);
        return sql ? <Tooltip title={sql}><code>{sql}</code></Tooltip> : '-';
      },
    },
    {
      title: '实际值',
      width: 120,
      ellipsis: true,
      render: (_: any, r: any) => {
        const actual = pick(r, ['actual', 'actual_value']);
        return actual === undefined || actual === null ? 'null' : String(actual);
      },
    },
    {
      title: '预期值',
      width: 120,
      ellipsis: true,
      render: (_: any, r: any) => {
        const expected = pick(r, ['expected', 'expected_value', 'expected_result']);
        if (expected === undefined || expected === null) return '-';
        return typeof expected === 'object' ? JSON.stringify(expected) : String(expected);
      },
    },
    {
      title: '结果',
      width: 80,
      render: (_: any, r: any) => {
        const passed = pick(r, ['passed', 'is_passed', 'success']);
        return passed ? <Tag color="green">通过</Tag> : <Tag color="red">失败</Tag>;
      },
    },
  ];

  return (
    <div className="report-workspace">
      <Card className="workspace-filter-card" style={{ marginBottom: 16 }}>
        <div className="workspace-filter-heading">
          <Space>
            <FilterOutlined />
            <Typography.Text strong>报告筛选</Typography.Text>
            <Tag color="green">项目服务端筛选</Tag>
          </Space>
          <Typography.Text type="secondary">
            项目条件由后端查询；来源、状态和时间在当前结果中即时筛选。
          </Typography.Text>
        </div>
        <div className="workspace-filter-grid">
          <div className="workspace-filter-item">
            <Typography.Text type="secondary">项目</Typography.Text>
            <Select
              allowClear
              placeholder="全部项目"
              value={selectedProjectId ?? undefined}
              onChange={(value) => setSelectedProjectId(value ?? null)}
              options={projects.map((project) => ({
                value: project.id,
                label: project.name,
              }))}
              showSearch
              optionFilterProp="label"
            />
          </div>
          <div className="workspace-filter-item">
            <Typography.Text type="secondary">来源 / 类型</Typography.Text>
            <Select
              allowClear
              placeholder="全部来源"
              value={sourceFilter}
              onChange={(value) => {
                setSourceFilter(value);
                setTrendFocusRunId(null);
              }}
              options={sourceOptions.map((source) => ({ value: source, label: source }))}
            />
          </div>
          <div className="workspace-filter-item">
            <Typography.Text type="secondary">状态</Typography.Text>
            <Select
              allowClear
              placeholder="全部状态"
              value={statusFilter}
              onChange={(value) => {
                setStatusFilter(value);
                setTrendFocusRunId(null);
              }}
              options={statusOptions.map((status) => ({
                value: status,
                label: statusLabel[status] || status,
              }))}
            />
          </div>
          <div className="workspace-filter-item workspace-filter-date">
            <Typography.Text type="secondary">执行时间</Typography.Text>
            <RangePicker
              value={dateRange}
              onChange={(value) => {
                setDateRange(value as [Dayjs, Dayjs] | null);
                setTrendFocusRunId(null);
              }}
              allowEmpty={[true, true]}
            />
          </div>
          <Button
            icon={<ReloadOutlined />}
            onClick={clearFilters}
            loading={loading}
          >
            清除并刷新
          </Button>
        </div>
        <div className="workspace-filter-feedback">
          <Typography.Text type="secondary">
            当前显示 {filteredRuns.length} 条记录
            {selectedProjectId ? '，项目范围由后端按全局工作区查询' : '，项目范围为全部项目'}
            {focusedRun ? '，列表已定位到趋势选中的批次' : ''}。
          </Typography.Text>
          {focusedRun && (
            <Button type="link" size="small" onClick={() => setTrendFocusRunId(null)}>
              查看全部筛选结果
            </Button>
          )}
        </div>
      </Card>

      {/* 顶部统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总执行次数"
              value={totalRuns}
              prefix={<ReloadOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总通过率"
              value={overallPassRate}
              precision={1}
              suffix="%"
              styles={{ content: {
                color: overallPassRate >= 80 ? '#3f8600' : '#cf1322',
              } }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总用例数"
              value={sumTotal}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均耗时"
              value={avgDuration}
              precision={2}
              suffix="s"
              prefix={<ExclamationCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 趋势图 */}
      <Card
        title={
          <Space>
            <span>通过率趋势（当前筛选最近 {trend.length} 次）</span>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => void loadData()}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        {trend.length === 0 ? (
          <Empty description="暂无趋势数据" style={{ padding: 40 }} />
        ) : (
          <div style={{ height: 340, width: '100%' }}>
            <canvas ref={trendCanvasRef} />
          </div>
        )}
        <Typography.Text type="secondary">
          点击趋势中的执行点，可联动定位下方对应批次。
        </Typography.Text>
      </Card>

      {/* 执行批次列表 */}
      <Card
        title={
          <Space>
            <span>执行批次</span>
            <Tag>{visibleRuns.length} 条</Tag>
          </Space>
        }
      >
        <Table
          dataSource={visibleRuns}
          rowKey={(record: any) => runIdOf(record) || JSON.stringify(record)}
          data-testid="reports-table"
          loading={loading}
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
          columns={columns}
          size="middle"
          scroll={{ x: 980 }}
          rowClassName={(record: any) =>
            runIdOf(record) === trendFocusRunId ? 'report-row-focused' : ''
          }
          locale={{ emptyText: <Empty description="暂无执行记录" /> }}
        />
      </Card>

      {/* 单次执行详情 Modal */}
      <Modal
        title="执行详情"
        open={detailOpen}
        onCancel={() => {
          setDetailOpen(false);
          setDetail(null);
        }}
        width={920}
        footer={
          <Button
            type="primary"
            onClick={() => {
              setDetailOpen(false);
              setDetail(null);
            }}
          >
            关闭
          </Button>
        }
        destroyOnHidden
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin description="加载中..." />
          </div>
        ) : detail ? (
          <div>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} lg={10}>
                <Card size="small" title="结果占比">
                  <div style={{ height: 220, width: '100%' }}>
                    <canvas ref={pieCanvasRef} />
                  </div>
                </Card>
              </Col>
              <Col xs={24} lg={14}>
                <Card size="small" title="执行概览">
                  <Row gutter={[16, 12]}>
                    <Col xs={12} md={8}>
                      <Statistic
                        title="总数"
                        value={Number(pick(detail, ['total'])) || 0}
                      />
                    </Col>
                    <Col xs={12} md={8}>
                      <Statistic
                        title="通过"
                        value={Number(pick(detail, ['passed'])) || 0}
                        styles={{ content: { color: '#52c41a' } }}
                        prefix={<CheckCircleOutlined />}
                      />
                    </Col>
                    <Col xs={12} md={8}>
                      <Statistic
                        title="失败"
                        value={Number(pick(detail, ['failed'])) || 0}
                        styles={{ content: { color: '#ff4d4f' } }}
                        prefix={<CloseCircleOutlined />}
                      />
                    </Col>
                    <Col xs={12} md={8}>
                      <Statistic
                        title="错误"
                        value={Number(pick(detail, ['error'])) || 0}
                        styles={{ content: { color: '#faad14' } }}
                        prefix={<ExclamationCircleOutlined />}
                      />
                    </Col>
                    <Col xs={12} md={8}>
                      <Statistic
                        title="总耗时"
                        value={Number(pick(detail, ['duration', 'duration_sum'])) || 0}
                        precision={2}
                        suffix="s"
                      />
                    </Col>
                    <Col xs={12} md={8}>
                      <Statistic
                        title="通过率"
                        value={
                          pick(detail, ['total']) > 0
                            ? ((Number(pick(detail, ['passed'])) || 0) /
                                (Number(pick(detail, ['total'])) || 1)) *
                                100
                            : 0
                        }
                        precision={1}
                        suffix="%"
                      />
                    </Col>
                  </Row>
                </Card>
              </Col>
            </Row>
            <Card size="small" title="详细结果列表">
              <Table
                dataSource={detailResults}
                rowKey={(record: any) =>
                  pick(record, ['id', 'test_case_id', 'case_id']) || JSON.stringify(record)
                }
                size="small"
                pagination={{ pageSize: 8 }}
                columns={resultColumns}
                locale={{ emptyText: '暂无详细结果' }}
              />
            </Card>
            {/* 数据库断言结果面板：仅在后端返回 db_results 时展示 */}
            {dbAssertionResults.length > 0 && (
              <Card size="small" title="数据库断言结果" style={{ marginTop: 16 }}>
                <Table
                  dataSource={dbAssertionResults}
                  rowKey={(record: any) =>
                    pick(record, ['id', 'assertion_id', 'name']) || JSON.stringify(record)
                  }
                  size="small"
                  pagination={{ pageSize: 8 }}
                  columns={dbResultColumns}
                  locale={{ emptyText: '暂无数据库断言结果' }}
                />
              </Card>
            )}
          </div>
        ) : (
          <Empty description="暂无数据" />
        )}
      </Modal>
    </div>
  );
}
