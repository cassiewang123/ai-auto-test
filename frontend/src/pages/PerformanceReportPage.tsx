import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Space,
  Button,
  Row,
  Col,
  Statistic,
  message,
  Empty,
  Tabs,
  Badge,
  Select,
  Drawer,
  Spin,
} from 'antd';
import {
  BarChartOutlined,
  ThunderboltOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LineChartOutlined,
  DesktopOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { performanceTestApi } from '../services/api';

// 防御性取值：兼容后端可能返回的不同字段名
function pick(obj: any, keys: string[]): any {
  if (!obj) return undefined;
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  }
  return undefined;
}

function fmtMs(v: any): string {
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return `${n.toFixed(2)} ms`;
}

function errorRateColor(rate: number): string {
  if (rate >= 5) return '#cf1322';
  if (rate >= 1) return '#d4b106';
  return '#3f8600';
}

// SLA 状态徽章（功能16）
const slaBadgeStatus: Record<string, any> = {
  passed: 'success',
  failed: 'error',
  warning: 'warning',
};
const slaText: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  warning: '警告',
};

function pickSceneName(record: any): string {
  const detail = record?.detail;
  if (detail && typeof detail === 'object') {
    const name =
      pick(detail, ['name', 'test_name', 'scene_name', 'scenario_name']) ||
      pick(detail, ['title']);
    if (name) return String(name);
  }
  return record?.test_id || '-';
}

export default function PerformanceReportPage() {
  const [activeTab, setActiveTab] = useState('report');

  // 报告 Tab 数据
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // 服务器监控 Drawer（功能15）
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [monitorLoading, setMonitorLoading] = useState(false);
  const [monitorMetrics, setMonitorMetrics] = useState<any[]>([]);
  const [monitorRecord, setMonitorRecord] = useState<any>(null);

  // 趋势对比 Tab（功能18）
  const [testOptions, setTestOptions] = useState<{ label: string; value: string }[]>([]);
  const [selectedTestIds, setSelectedTestIds] = useState<string[]>([]);
  const [trendMetric, setTrendMetric] = useState('rps');
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendData, setTrendData] = useState<any>(null);

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await performanceTestApi.listAllResults({
        page: p,
        page_size: ps,
      });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadTestOptions() {
    try {
      const res = await performanceTestApi.list({ page: 1, page_size: 100 });
      const opts = (res.data || []).map((t: any) => ({ label: t.name, value: t.id }));
      setTestOptions(opts);
    } catch {
      /* 忽略 */
    }
  }

  useEffect(() => {
    loadData(1);
    loadTestOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 顶部统计
  const totalRuns = total;
  const sumRequests = data.reduce(
    (s, r) => s + (Number(pick(r, ['total_requests'])) || 0),
    0
  );
  const avgErrorRate =
    data.length > 0
      ? data.reduce((s, r) => s + (Number(pick(r, ['error_rate'])) || 0), 0) /
        data.length
      : 0;
  const avgResponseTime =
    data.length > 0
      ? data.reduce(
          (s, r) => s + (Number(pick(r, ['avg_response_time'])) || 0),
          0
        ) / data.length
      : 0;

  // 查看服务器监控（功能15）
  async function openMonitor(record: any) {
    setMonitorRecord(record);
    setMonitorOpen(true);
    setMonitorLoading(true);
    setMonitorMetrics([]);
    try {
      const res = await performanceTestApi.getMetrics(record.test_id, record.id);
      setMonitorMetrics(res?.data?.metrics || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setMonitorLoading(false);
    }
  }

  // 查询趋势对比（功能18）
  async function loadTrends() {
    if (selectedTestIds.length === 0) {
      message.warning('请至少选择一个压测场景');
      return;
    }
    setTrendLoading(true);
    try {
      const res = await performanceTestApi.getTrends(selectedTestIds, trendMetric);
      setTrendData(res?.data || null);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setTrendLoading(false);
    }
  }

  function expandDetail(detail: any): any[] {
    if (!detail || typeof detail !== 'object') return [];
    if (Array.isArray(detail)) return detail;
    const arr = pick(detail, ['cases', 'results', 'items', 'details', 'per_case']);
    if (Array.isArray(arr)) return arr;
    const entries = Object.entries(detail).filter(
      ([k]) => !['name', 'test_name', 'scene_name', 'scenario_name', 'title'].includes(k)
    );
    if (entries.length === 0) return [];
    return entries.map(([k, v]) =>
      v && typeof v === 'object' ? { name: k, ...(v as object) } : { name: k, value: v }
    );
  }

  const detailColumns = [
    {
      title: '用例/接口',
      width: 220,
      ellipsis: true,
      render: (_: any, r: any) =>
        pick(r, ['name', 'title', 'case_name', 'case_title', 'url']) ||
        pick(r, ['case_id', 'id']) ||
        '-',
    },
    {
      title: '请求数',
      width: 90,
      align: 'center' as const,
      render: (_: any, r: any) =>
        Number(pick(r, ['total_requests', 'requests', 'count'])) || 0,
    },
    {
      title: '成功',
      width: 80,
      align: 'center' as const,
      render: (_: any, r: any) => (
        <span style={{ color: '#3f8600' }}>
          {Number(pick(r, ['success_requests', 'success'])) || 0}
        </span>
      ),
    },
    {
      title: '失败',
      width: 80,
      align: 'center' as const,
      render: (_: any, r: any) => (
        <span style={{ color: '#cf1322' }}>
          {Number(pick(r, ['fail_requests', 'fail', 'failed'])) || 0}
        </span>
      ),
    },
    {
      title: '错误率',
      width: 90,
      render: (_: any, r: any) => {
        const rate = Number(pick(r, ['error_rate'])) || 0;
        return (
          <span style={{ color: errorRateColor(rate), fontWeight: 600 }}>
            {rate.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: '平均响应',
      width: 110,
      render: (_: any, r: any) => fmtMs(pick(r, ['avg_response_time', 'avg'])),
    },
    {
      title: 'P95',
      width: 100,
      render: (_: any, r: any) => fmtMs(pick(r, ['p95'])),
    },
    {
      title: 'RPS',
      width: 90,
      render: (_: any, r: any) => {
        const v = Number(pick(r, ['rps'])) || 0;
        return v.toFixed(2);
      },
    },
  ];

  const columns = [
    {
      title: '场景名称',
      width: 180,
      ellipsis: true,
      render: (_: any, record: any) => pickSceneName(record),
    },
    {
      title: 'SLA',
      width: 90,
      align: 'center' as const,
      render: (_: any, record: any) => {
        const st = pick(record, ['sla_status']);
        if (!st) return <span style={{ color: '#9ca3af' }}>-</span>;
        return (
          <Badge
            status={slaBadgeStatus[st] || 'default'}
            text={slaText[st] || st}
          />
        );
      },
    },
    {
      title: '运行时间',
      dataIndex: 'created_at',
      width: 150,
      render: (t: string) => (t ? dayjs(t).format('MM-DD HH:mm') : '-'),
    },
    {
      title: '总请求数',
      dataIndex: 'total_requests',
      width: 90,
      align: 'center' as const,
      render: (v: number) => v || 0,
    },
    {
      title: '错误率',
      dataIndex: 'error_rate',
      width: 90,
      render: (v: number) => {
        const rate = Number(v) || 0;
        return (
          <span style={{ color: errorRateColor(rate), fontWeight: 600 }}>
            {rate.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: 'P95',
      dataIndex: 'p95',
      width: 90,
      render: (v: number) => fmtMs(v),
    },
    {
      title: 'RPS',
      dataIndex: 'rps',
      width: 80,
      render: (v: number) => (Number(v) || 0).toFixed(2),
    },
    {
      title: '操作',
      width: 110,
      render: (_: any, record: any) => (
        <Button
          size="small"
          icon={<DesktopOutlined />}
          onClick={() => openMonitor(record)}
        >
          监控
        </Button>
      ),
    },
  ];

  // 趋势对比表格数据
  const trendSeries = trendData?.series || [];
  const trendTableData = trendSeries.map((s: any) => {
    const values = (s.points || []).map((p: any) => Number(p.value) || 0);
    const latest = values.length ? values[values.length - 1] : 0;
    const avg = values.length ? values.reduce((a: number, b: number) => a + b, 0) / values.length : 0;
    const max = values.length ? Math.max(...values) : 0;
    const min = values.length ? Math.min(...values) : 0;
    return {
      key: s.test_id,
      test_name: s.test_name,
      count: values.length,
      latest: Number(latest.toFixed(2)),
      avg: Number(avg.toFixed(2)),
      max: Number(max.toFixed(2)),
      min: Number(min.toFixed(2)),
    };
  });

  const trendColumns = [
    { title: '场景', dataIndex: 'test_name', width: 180, ellipsis: true },
    { title: '压测次数', dataIndex: 'count', width: 90, align: 'center' as const },
    { title: '最新值', dataIndex: 'latest', width: 100, align: 'right' as const },
    { title: '平均值', dataIndex: 'avg', width: 100, align: 'right' as const },
    { title: '最大值', dataIndex: 'max', width: 100, align: 'right' as const },
    { title: '最小值', dataIndex: 'min', width: 100, align: 'right' as const },
  ];

  // 趋势折线图数据：合并多场景为按时间索引的数组
  const trendChartData: any[] = [];
  if (trendSeries.length > 0) {
    const maxLen = Math.max(...trendSeries.map((s: any) => (s.points || []).length));
    for (let i = 0; i < maxLen; i++) {
      const row: any = { idx: i + 1 };
      trendSeries.forEach((s: any) => {
        const p = (s.points || [])[i];
        row[s.test_name] = p ? Number(p.value) || 0 : null;
      });
      trendChartData.push(row);
    }
  }

  const metricLabel: Record<string, string> = {
    rps: 'RPS',
    p95: 'P95 (ms)',
    p99: 'P99 (ms)',
    error_rate: '错误率 (%)',
    avg_response_time: '平均响应 (ms)',
  };

  return (
    <div>
      {/* 顶部统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总压测次数"
              value={totalRuns}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总请求数"
              value={sumRequests}
              prefix={<BarChartOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均错误率"
              value={avgErrorRate}
              precision={2}
              suffix="%"
              styles={{ content: { color: errorRateColor(avgErrorRate) } }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均响应时间"
              value={avgResponseTime}
              precision={2}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'report',
              label: (
                <span>
                  <BarChartOutlined /> 性能报告
                </span>
              ),
              children: (
                <>
                  <div style={{ marginBottom: 12, color: '#6b7280', fontSize: 13 }}>
                    共 {total} 条结果 · 点击行可展开查看用例明细 · 点击「监控」查看服务器资源占用
                  </div>
                  <Table
                    dataSource={data}
                    rowKey={(record: any) =>
                      pick(record, ['id']) ||
                      `${pick(record, ['run_id'])}-${pick(record, ['test_id'])}` ||
                      JSON.stringify(record)
                    }
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
                    locale={{ emptyText: <Empty description="暂无压测结果" /> }}
                    expandable={{
                      rowExpandable: (record: any) => {
                        const rows = expandDetail(record?.detail);
                        return rows.length > 0;
                      },
                      expandedRowRender: (record: any) => {
                        const rows = expandDetail(record?.detail);
                        if (rows.length === 0) {
                          return <Empty description="暂无用例明细" style={{ padding: 16 }} />;
                        }
                        return (
                          <Table
                            dataSource={rows}
                            rowKey={(record: any) =>
                              pick(record, ['id', 'case_id', 'name']) || JSON.stringify(record)
                            }
                            columns={detailColumns}
                            size="small"
                            pagination={false}
                            locale={{ emptyText: '暂无用例明细' }}
                          />
                        );
                      },
                    }}
                  />
                </>
              ),
            },
            {
              key: 'trend',
              label: (
                <span>
                  <LineChartOutlined /> 趋势对比
                </span>
              ),
              children: (
                <div>
                  <Space style={{ marginBottom: 16 }} size="middle">
                    <Select
                      mode="multiple"
                      allowClear
                      placeholder="选择 2-5 个压测场景"
                      style={{ minWidth: 360 }}
                      maxTagCount="responsive"
                      options={testOptions}
                      value={selectedTestIds}
                      onChange={setSelectedTestIds}
                    />
                    <Select
                      style={{ width: 180 }}
                      value={trendMetric}
                      onChange={setTrendMetric}
                      options={[
                        { label: 'RPS', value: 'rps' },
                        { label: 'P95 响应时间', value: 'p95' },
                        { label: 'P99 响应时间', value: 'p99' },
                        { label: '错误率', value: 'error_rate' },
                        { label: '平均响应时间', value: 'avg_response_time' },
                      ]}
                    />
                    <Button type="primary" loading={trendLoading} onClick={loadTrends}>
                      查询对比
                    </Button>
                  </Space>

                  {trendTableData.length > 0 && (
                    <>
                      <Card size="small" title="指标对比表" style={{ marginBottom: 16 }}>
                        <Table
                          dataSource={trendTableData}
                          columns={trendColumns}
                          size="small"
                          pagination={false}
                        />
                      </Card>
                      <Card
                        size="small"
                        title={`${metricLabel[trendMetric] || trendMetric} 趋势图`}
                      >
                        <ResponsiveContainer width="100%" height={320}>
                          <LineChart data={trendChartData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="idx" name="第N次" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            {trendSeries.map((s: any) => (
                              <Line
                                key={s.test_id}
                                type="monotone"
                                dataKey={s.test_name}
                                connectNulls
                                dot
                              />
                            ))}
                          </LineChart>
                        </ResponsiveContainer>
                      </Card>
                    </>
                  )}
                  {trendData && trendTableData.length === 0 && (
                    <Empty description="所选场景暂无历史结果" />
                  )}
                  {!trendData && (
                    <Empty description="请选择压测场景并点击查询" />
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 服务器监控 Drawer（功能15） */}
      <Drawer
        title={
          <Space>
            <DesktopOutlined />
            <span>服务器监控 - {pickSceneName(monitorRecord)}</span>
          </Space>
        }
        open={monitorOpen}
        onClose={() => setMonitorOpen(false)}
        size={720}
      >
        {monitorLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin description="加载监控数据..." />
          </div>
        ) : monitorMetrics.length === 0 ? (
          <Empty description="暂无监控数据" />
        ) : (
          <div>
            <Card size="small" title="CPU / 内存使用率 (%)" style={{ marginBottom: 16 }}>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={monitorMetrics}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="elapsed" name="秒" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip labelFormatter={(v) => `${v} s`} />
                  <Legend />
                  <Line type="monotone" dataKey="cpu" stroke="#4f46e5" name="CPU%" dot={false} />
                  <Line type="monotone" dataKey="memory" stroke="#059669" name="内存%" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
            <Card size="small" title="磁盘 / 网络 IO (KB/s)" style={{ marginBottom: 16 }}>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={monitorMetrics}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="elapsed" name="秒" />
                  <YAxis />
                  <Tooltip labelFormatter={(v) => `${v} s`} />
                  <Legend />
                  <Line type="monotone" dataKey="disk_read" stroke="#0891b2" name="磁盘读" dot={false} />
                  <Line type="monotone" dataKey="disk_write" stroke="#d97706" name="磁盘写" dot={false} />
                  <Line type="monotone" dataKey="net_sent" stroke="#dc2626" name="网络发送" dot={false} />
                  <Line type="monotone" dataKey="net_recv" stroke="#7c3aed" name="网络接收" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
            <Card size="small" title="监控明细">
              <Table
                dataSource={monitorMetrics}
                rowKey={(record: any) =>
                  String(pick(record, ['id', 'timestamp', 'elapsed']) ?? JSON.stringify(record))
                }
                size="small"
                pagination={{ pageSize: 8, size: 'small' }}
                scroll={{ x: 600 }}
                columns={[
                  { title: '秒', dataIndex: 'elapsed', width: 70 },
                  { title: 'CPU%', dataIndex: 'cpu', width: 80 },
                  { title: '内存%', dataIndex: 'memory', width: 80 },
                  { title: '磁盘读', dataIndex: 'disk_read', width: 90 },
                  { title: '磁盘写', dataIndex: 'disk_write', width: 90 },
                  { title: '网络发送', dataIndex: 'net_sent', width: 90 },
                  { title: '网络接收', dataIndex: 'net_recv', width: 90 },
                ]}
              />
            </Card>
          </div>
        )}
      </Drawer>
    </div>
  );
}
