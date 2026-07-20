import { useEffect, useRef, useState } from 'react';
import {
  Card,
  Space,
  Select,
  Button,
  Row,
  Col,
  Statistic,
  message,
  Empty,
  Spin,
  Badge,
  Tag,
  Alert,
  Descriptions,
} from 'antd';
import {
  ReloadOutlined,
  DashboardOutlined,
  ThunderboltOutlined,
  PlayCircleOutlined,
  StopOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined,
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
import '../styles/perf-dashboard-workspace.css';

// 压测状态徽章颜色
const statusColor: Record<string, string> = {
  idle: 'default',
  running: 'processing',
  completed: 'green',
  failed: 'red',
};

const statusLabel: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

// 压测模式标签
const modeLabel: Record<string, string> = {
  steady: '稳定',
  ramp: '阶梯',
  peak: '峰值',
  custom: '自定义',
  constant: '稳定',
  step: '阶梯',
  surge: '突发',
  soak: '浸泡',
};

// 错误率着色
function errorRateColor(rate: number): string {
  if (rate >= 5) return '#cf1322';
  if (rate >= 1) return '#d4b106';
  return '#3f8600';
}

function fmtMs(v: any): string {
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return `${n.toFixed(2)} ms`;
}

function fmtSec(v: any): string {
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return `${n.toFixed(2)} s`;
}

function finiteNumber(value: any): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

type MetricTone = 'success' | 'warning' | 'error' | 'default';

function metricTone(
  actual: number | undefined,
  threshold: number | undefined,
  direction: 'max' | 'min'
): MetricTone {
  if (actual === undefined || threshold === undefined) return 'default';
  if (direction === 'max') {
    if (actual > threshold) return 'error';
    if (threshold > 0 && actual > threshold * 0.9) return 'warning';
    return 'success';
  }
  if (actual < threshold) return 'error';
  if (threshold > 0 && actual < threshold * 1.1) return 'warning';
  return 'success';
}

function slaStatusText(status: string | null | undefined): string {
  if (status === 'passed') return 'SLA 已通过';
  if (status === 'failed') return 'SLA 未通过';
  if (status === 'warning') return 'SLA 接近阈值';
  return 'SLA 待评估';
}

function slaStatusIcon(status: string | null | undefined) {
  if (status === 'passed') return <CheckCircleOutlined />;
  if (status === 'failed') return <CloseCircleOutlined />;
  if (status === 'warning') return <WarningOutlined />;
  return <ClockCircleOutlined />;
}

export default function PerfDashboardPage() {
  const [scenes, setScenes] = useState<any[]>([]);
  const [sceneId, setSceneId] = useState<string | undefined>(undefined);
  const [scenesLoading, setScenesLoading] = useState(false);

  // 实时数据
  const [realtime, setRealtime] = useState<any>(null);
  const [polling, setPolling] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeSceneIdRef = useRef<string | undefined>(undefined);

  // 最近一次结果摘要（非运行中时展示）
  const [lastResult, setLastResult] = useState<any>(null);

  // 加载压测场景列表
  async function loadScenes() {
    setScenesLoading(true);
    try {
      const res = await performanceTestApi.list({ page: 1, page_size: 100 });
      const list = res.data || [];
      setScenes(list);
      setSceneId((currentId) =>
        list.some((scene: any) => scene.id === currentId)
          ? currentId
          : list[0]?.id
      );
      return list;
    } catch (e: any) {
      message.error(e.message);
      return [];
    } finally {
      setScenesLoading(false);
    }
  }

  // 拉取一次实时数据
  async function fetchRealtime(id: string) {
    try {
      const rt = await performanceTestApi.getRealtime(id);
      const data = rt?.data;
      if (activeSceneIdRef.current === id) {
        setRealtime(data || null);
      }
      return data?.status;
    } catch (e: any) {
      // 忽略单次轮询错误，避免噪音
      return undefined;
    }
  }

  // 拉取最近一次结果
  async function fetchLastResult(id: string) {
    try {
      const res = await performanceTestApi.getResults(id, { page: 1, page_size: 1 });
      const result = res?.data?.[0] || null;
      if (activeSceneIdRef.current === id) {
        setLastResult(result);
      }
      return result;
    } catch {
      if (activeSceneIdRef.current === id) {
        setLastResult(null);
      }
      return null;
    }
  }

  useEffect(() => {
    loadScenes();
    return () => {
      // 组件卸载清理定时器
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 场景切换时停止轮询并拉取一次
  useEffect(() => {
    activeSceneIdRef.current = sceneId;
    stopPolling();
    setRealtime(null);
    setLastResult(null);
    if (!sceneId) return;

    let active = true;
    void Promise.all([
      fetchRealtime(sceneId),
      fetchLastResult(sceneId),
    ]).then(([initialStatus]) => {
      if (
        active &&
        activeSceneIdRef.current === sceneId &&
        initialStatus === 'running'
      ) {
        startPolling(sceneId);
      }
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId]);

  // 启动轮询
  function startPolling(targetSceneId = sceneId) {
    if (!targetSceneId) {
      message.warning('请先选择压测场景');
      return;
    }
    stopPolling();
    setPolling(true);

    const poll = async () => {
      if (activeSceneIdRef.current !== targetSceneId) return;
      const status = await fetchRealtime(targetSceneId);
      if (activeSceneIdRef.current !== targetSceneId) return;
      if (status === 'completed' || status === 'failed') {
        stopPolling();
        await fetchLastResult(targetSceneId);
        if (status === 'completed') {
          message.success('压测已完成');
        } else {
          message.error('压测执行失败');
        }
        return;
      }
      pollTimerRef.current = setTimeout(() => {
        void poll();
      }, 2000);
    };

    void poll();
  }

  // 停止轮询
  function stopPolling() {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setPolling(false);
  }

  // 触发后台压测并开始轮询
  async function handleRun() {
    if (!sceneId) {
      message.warning('请先选择压测场景');
      return;
    }
    const targetSceneId = sceneId;
    try {
      await performanceTestApi.run(targetSceneId);
      message.success('压测已启动');
      if (activeSceneIdRef.current === targetSceneId) {
        startPolling(targetSceneId);
      }
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleRefresh() {
    const targetSceneId = sceneId;
    await loadScenes();
    if (!targetSceneId || activeSceneIdRef.current !== targetSceneId) return;
    const [currentStatus] = await Promise.all([
      fetchRealtime(targetSceneId),
      fetchLastResult(targetSceneId),
    ]);
    if (currentStatus === 'running' && !polling) {
      startPolling(targetSceneId);
    }
  }

  // 清理实时内存
  async function handleClear() {
    if (!sceneId) return;
    const targetSceneId = sceneId;
    try {
      await performanceTestApi.clearRealtime(targetSceneId);
      message.success('已清理实时数据');
      await fetchRealtime(targetSceneId);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 当前选中场景对象
  const currentScene = scenes.find((s) => s.id === sceneId);

  // 实时状态字段
  const status = realtime?.status || currentScene?.status || 'idle';
  const runId = realtime?.run_id || null;
  const error = realtime?.error || null;
  const latest = realtime?.latest || null;
  const snapshots: any[] = realtime?.snapshots || [];

  // 实时数字卡片
  const activeUsers = Number(latest?.active_users ?? 0);
  const instRps = Number(latest?.rps ?? 0);
  const totalReq = Number(latest?.total_requests ?? 0);
  const failReq = Number(latest?.fail_requests ?? 0);
  const avgRt = Number(latest?.avg_rt ?? 0);
  const errRate = Number(latest?.error_rate ?? 0);

  // 最近一次结果摘要
  const r = lastResult || {};
  const lrErrRate = Number(r.error_rate ?? 0);
  const lrP95 = r.p95;
  const lrP99 = r.p99;
  const lrRps = Number(r.rps ?? 0);
  const lrSla = r.sla_status;
  const lrMode = r.mode || currentScene?.config?.mode;

  const isRunning = status === 'running';
  const hasLastResult = Boolean(lastResult);
  const slaConfig = currentScene?.config?.sla || {};
  const slaDetails = r.sla_details || {};

  const p95Threshold = finiteNumber(
    slaDetails.response_time_p95?.threshold ?? slaConfig.response_time_p95
  );
  const errorThresholdFraction = finiteNumber(
    slaDetails.error_rate?.threshold ?? slaConfig.error_rate
  );
  const errorThreshold =
    errorThresholdFraction === undefined ? undefined : errorThresholdFraction * 100;
  const rpsThreshold = finiteNumber(slaDetails.rps_min?.threshold ?? slaConfig.rps_min);

  const realtimeP95 = finiteNumber(latest?.p95);
  const realtimeP99 = finiteNumber(latest?.p99);
  const headlineP95 = realtimeP95 ?? finiteNumber(hasLastResult ? lrP95 : undefined);
  const headlineP99 = realtimeP99 ?? finiteNumber(hasLastResult ? lrP99 : undefined);
  const headlineErrorRate = isRunning
    ? finiteNumber(latest?.error_rate)
    : hasLastResult
      ? lrErrRate
      : undefined;
  const headlineRps = isRunning ? finiteNumber(latest?.rps) : hasLastResult ? lrRps : undefined;
  const p95Source =
    realtimeP95 !== undefined
      ? '实时数据'
      : hasLastResult
        ? '最近一次结果'
        : '等待执行';
  const p99Source =
    realtimeP99 !== undefined
      ? '实时数据'
      : hasLastResult
        ? '最近一次结果'
        : '等待执行';
  const realtimeMetricSource = isRunning
    ? '实时数据'
    : hasLastResult
      ? '最近一次结果'
      : '等待执行';
  const effectiveSlaStatus = isRunning ? null : lrSla;

  const thresholdTags = [
    p95Threshold === undefined
      ? null
      : {
          key: 'p95',
          label: `P95 ≤ ${p95Threshold.toFixed(0)} ms`,
          status: slaDetails.response_time_p95?.status,
        },
    errorThreshold === undefined
      ? null
      : {
          key: 'error-rate',
          label: `错误率 ≤ ${errorThreshold.toFixed(2)}%`,
          status: slaDetails.error_rate?.status,
        },
    rpsThreshold === undefined
      ? null
      : {
          key: 'rps',
          label: `RPS ≥ ${rpsThreshold.toFixed(2)}`,
          status: slaDetails.rps_min?.status,
        },
  ].filter(Boolean) as Array<{ key: string; label: string; status?: string }>;

  return (
    <div className="perf-dashboard-workspace">
      <header className="perf-dashboard-header">
        <div className="perf-dashboard-title">
          <div className="perf-dashboard-title__heading">
            <DashboardOutlined />
            <span>性能实时仪表盘</span>
            <Badge
              status={(statusColor[status] as any) || 'default'}
              text={statusLabel[status] || status}
            />
          </div>
          <span className="perf-dashboard-title__scene">
            {currentScene?.name || '选择场景后查看指标'}
          </span>
        </div>

        <div className="perf-dashboard-actions">
          <Select
            className="perf-dashboard-scene-select"
            showSearch
            optionFilterProp="label"
            placeholder="选择压测场景"
            value={sceneId}
            loading={scenesLoading}
            options={scenes.map((s) => ({
              label: `${s.name}${s.config?.mode ? `（${modeLabel[s.config.mode] || s.config.mode}）` : ''}`,
              value: s.id,
            }))}
            onChange={(v) => setSceneId(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
            刷新
          </Button>
          {!isRunning ? (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleRun}
              disabled={!sceneId}
            >
              启动压测
            </Button>
          ) : polling ? (
            <Button danger icon={<StopOutlined />} onClick={stopPolling}>
              停止轮询
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => startPolling()}
            >
              继续轮询
            </Button>
          )}
          {polling && (
            <Tag color="processing" icon={<ThunderboltOutlined />}>
              2s 刷新
            </Tag>
          )}
        </div>
      </header>

      {!sceneId ? (
        <Card className="perf-dashboard-empty">
          <Empty description="请选择压测场景" />
        </Card>
      ) : (
        <>
          {error && <Alert type="error" showIcon title="压测执行出错" description={error} />}

          <section
            className={`perf-sla-summary perf-sla-summary--${
              isRunning ? 'running' : effectiveSlaStatus || 'pending'
            }`}
          >
            <div className="perf-sla-summary__status">
              <span className="perf-sla-summary__icon">
                {isRunning ? <ThunderboltOutlined /> : slaStatusIcon(effectiveSlaStatus)}
              </span>
              <div>
                <strong>{isRunning ? '实时压测进行中' : slaStatusText(effectiveSlaStatus)}</strong>
                <span>
                  {isRunning
                    ? '压测结束后生成最终 SLA 结论'
                    : hasLastResult
                      ? `执行于 ${dayjs(r.created_at).format('YYYY-MM-DD HH:mm:ss')}`
                      : '完成首次压测后生成 SLA 结论'}
                </span>
              </div>
            </div>
            <div className="perf-sla-summary__thresholds">
              {thresholdTags.length > 0 ? (
                thresholdTags.map((item) => (
                  <Tag
                    key={item.key}
                    color={
                      item.status === 'pass'
                        ? 'success'
                        : item.status === 'fail'
                          ? 'error'
                          : item.status === 'warning'
                            ? 'warning'
                            : 'default'
                    }
                  >
                    {item.label}
                  </Tag>
                ))
              ) : (
                <span>当前场景未配置 SLA 阈值</span>
              )}
            </div>
          </section>

          <Row gutter={[12, 12]} className="perf-headline-metrics">
            <Col xs={24} sm={12} xl={6}>
              <HeadlineMetric
                title="P95 响应时间"
                value={headlineP95}
                suffix="ms"
                precision={2}
                source={p95Source}
                threshold={
                  p95Threshold === undefined ? undefined : `目标 ≤ ${p95Threshold.toFixed(0)} ms`
                }
                tone={metricTone(headlineP95, p95Threshold, 'max')}
              />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <HeadlineMetric
                title="P99 响应时间"
                value={headlineP99}
                suffix="ms"
                precision={2}
                source={p99Source}
              />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <HeadlineMetric
                title="错误率"
                value={headlineErrorRate}
                suffix="%"
                precision={2}
                source={realtimeMetricSource}
                threshold={
                  errorThreshold === undefined ? undefined : `目标 ≤ ${errorThreshold.toFixed(2)}%`
                }
                tone={metricTone(headlineErrorRate, errorThreshold, 'max')}
              />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <HeadlineMetric
                title="吞吐量"
                value={headlineRps}
                suffix="RPS"
                precision={2}
                source={realtimeMetricSource}
                threshold={
                  rpsThreshold === undefined ? undefined : `目标 ≥ ${rpsThreshold.toFixed(2)}`
                }
                tone={metricTone(headlineRps, rpsThreshold, 'min')}
              />
            </Col>
          </Row>

          {isRunning ? (
            <>
              <div className="perf-section-heading">
                <div>
                  <strong>实时负载</strong>
                  <span>{snapshots.length} 个采样点</span>
                </div>
                {runId && <Tag>run_id: {runId.slice(0, 8)}…</Tag>}
              </div>

              <Row gutter={[12, 12]} className="perf-live-metrics">
                <Col xs={12} md={8} xl={4}>
                  <Card size="small">
                    <Statistic
                      title="当前用户数"
                      value={activeUsers}
                      prefix={<ThunderboltOutlined />}
                    />
                  </Card>
                </Col>
                <Col xs={12} md={8} xl={4}>
                  <Card size="small">
                    <Statistic title="瞬时 RPS" value={instRps} precision={2} />
                  </Card>
                </Col>
                <Col xs={12} md={8} xl={4}>
                  <Card size="small">
                    <Statistic title="总请求数" value={totalReq} />
                  </Card>
                </Col>
                <Col xs={12} md={8} xl={4}>
                  <Card size="small">
                    <Statistic
                      title="失败请求数"
                      value={failReq}
                      styles={{ content: { color: failReq > 0 ? '#cf1322' : '#3f8600' } }}
                    />
                  </Card>
                </Col>
                <Col xs={12} md={8} xl={4}>
                  <Card size="small">
                    <Statistic title="平均响应时间" value={avgRt} precision={2} suffix="ms" />
                  </Card>
                </Col>
                <Col xs={12} md={8} xl={4}>
                  <Card size="small">
                    <Statistic
                      title="错误率"
                      value={errRate}
                      precision={2}
                      suffix="%"
                      styles={{ content: { color: errorRateColor(errRate) } }}
                    />
                  </Card>
                </Col>
              </Row>

              <Row gutter={[12, 12]} className="perf-chart-grid">
                <Col xs={24} xl={12}>
                  <TrendChartCard
                    title="RPS（每秒请求数）"
                    data={snapshots}
                    loading={polling}
                    lines={[{ dataKey: 'rps', name: 'RPS', stroke: '#4f46e5' }]}
                  />
                </Col>
                <Col xs={24} xl={12}>
                  <TrendChartCard
                    title="平均响应时间"
                    data={snapshots}
                    loading={polling}
                    yUnit="ms"
                    lines={[{ dataKey: 'avg_rt', name: '平均响应时间', stroke: '#0891b2' }]}
                  />
                </Col>
                <Col xs={24} xl={12}>
                  <TrendChartCard
                    title="错误率"
                    data={snapshots}
                    loading={polling}
                    yUnit="%"
                    lines={[{ dataKey: 'error_rate', name: '错误率', stroke: '#dc2626' }]}
                  />
                </Col>
                <Col xs={24} xl={12}>
                  <TrendChartCard
                    title="用户与请求趋势"
                    data={snapshots}
                    loading={polling}
                    showLegend
                    lines={[
                      {
                        dataKey: 'active_users',
                        name: '活跃用户',
                        stroke: '#059669',
                        type: 'stepAfter',
                      },
                      {
                        dataKey: 'total_requests',
                        name: '累计请求',
                        stroke: '#6366f1',
                      },
                    ]}
                  />
                </Col>
              </Row>

              {hasLastResult && (
                <LatestResultCard
                  title="上一次完成结果"
                  result={r}
                  mode={lrMode}
                  onClear={handleClear}
                />
              )}
            </>
          ) : (
            <Row gutter={[12, 12]} className="perf-idle-workspace">
              <Col xs={24} xl={17}>
                <LatestResultCard
                  title="最近一次结果"
                  result={hasLastResult ? r : null}
                  mode={lrMode}
                  onClear={handleClear}
                />
              </Col>
              <Col xs={24} xl={7}>
                <Card className="perf-launch-card">
                  <div className="perf-launch-card__icon">
                    <PlayCircleOutlined />
                  </div>
                  <div>
                    <strong>启动新一轮压测</strong>
                    <span>{currentScene?.name}</span>
                  </div>
                  <div className="perf-launch-card__meta">
                    {lrMode && <Tag color="blue">{modeLabel[lrMode] || lrMode}</Tag>}
                    {currentScene?.config?.users != null && (
                      <Tag>{currentScene.config.users} 用户</Tag>
                    )}
                    {currentScene?.config?.duration != null && (
                      <Tag>{currentScene.config.duration} 秒</Tag>
                    )}
                  </div>
                  <Button
                    type="primary"
                    size="large"
                    block
                    icon={<PlayCircleOutlined />}
                    onClick={handleRun}
                  >
                    启动压测
                  </Button>
                </Card>
              </Col>
            </Row>
          )}
        </>
      )}
    </div>
  );
}

function HeadlineMetric({
  title,
  value,
  suffix,
  precision,
  source,
  threshold,
  tone = 'default',
}: {
  title: string;
  value: number | undefined;
  suffix: string;
  precision: number;
  source: string;
  threshold?: string;
  tone?: MetricTone;
}) {
  return (
    <Card className={`perf-headline-metric perf-headline-metric--${tone}`} size="small">
      <Statistic
        title={title}
        value={value ?? '-'}
        precision={value === undefined ? undefined : precision}
        suffix={value === undefined ? undefined : suffix}
      />
      <div className="perf-headline-metric__footer">
        <span>{source}</span>
        {threshold && <strong>{threshold}</strong>}
      </div>
    </Card>
  );
}

function LatestResultCard({
  title,
  result,
  mode,
  onClear,
}: {
  title: string;
  result: any;
  mode?: string;
  onClear: () => void;
}) {
  return (
    <Card
      className="perf-latest-result"
      title={
        <Space wrap>
          <span>{title}</span>
          {result?.sla_status && (
            <Badge
              status={
                result.sla_status === 'passed'
                  ? 'success'
                  : result.sla_status === 'failed'
                    ? 'error'
                    : 'warning'
              }
              text={slaStatusText(result.sla_status)}
            />
          )}
          {mode && <Tag color="blue">{modeLabel[mode] || mode}</Tag>}
        </Space>
      }
      extra={
        <Button size="small" onClick={onClear}>
          清理实时数据
        </Button>
      }
    >
      {!result ? (
        <Empty description="暂无历史结果" />
      ) : (
        <Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
          <Descriptions.Item label="总请求数">
            {Number(result.total_requests ?? 0)}
          </Descriptions.Item>
          <Descriptions.Item label="成功数">
            <span style={{ color: '#3f8600' }}>{Number(result.success_requests ?? 0)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="失败数">
            <span style={{ color: '#cf1322' }}>{Number(result.fail_requests ?? 0)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="错误率">
            <span style={{ color: errorRateColor(Number(result.error_rate ?? 0)) }}>
              {Number(result.error_rate ?? 0).toFixed(2)}%
            </span>
          </Descriptions.Item>
          <Descriptions.Item label="平均响应时间">
            {fmtMs(result.avg_response_time)}
          </Descriptions.Item>
          <Descriptions.Item label="P95">{fmtMs(result.p95)}</Descriptions.Item>
          <Descriptions.Item label="P99">{fmtMs(result.p99)}</Descriptions.Item>
          <Descriptions.Item label="RPS">{Number(result.rps ?? 0).toFixed(2)}</Descriptions.Item>
          <Descriptions.Item label="持续时间" span={{ xs: 1, sm: 1, lg: 2 }}>
            {fmtSec(result.duration)}
          </Descriptions.Item>
          <Descriptions.Item label="执行时间" span={{ xs: 1, sm: 1, lg: 2 }}>
            {result.created_at ? dayjs(result.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
          </Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
}

type TrendLine = {
  dataKey: string;
  name: string;
  stroke: string;
  type?: 'monotone' | 'stepAfter';
};

function TrendChartCard({
  title,
  data,
  loading,
  lines,
  yUnit,
  showLegend = false,
}: {
  title: string;
  data: any[];
  loading: boolean;
  lines: TrendLine[];
  yUnit?: string;
  showLegend?: boolean;
}) {
  return (
    <Card className="perf-chart-card" size="small" title={title}>
      {data.length === 0 ? (
        <EmptyBox loading={loading} />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="t" name="时间" unit="s" fontSize={12} />
            <YAxis fontSize={12} unit={yUnit} />
            <Tooltip />
            {showLegend && <Legend />}
            {lines.map((line) => (
              <Line
                key={line.dataKey}
                type={line.type || 'monotone'}
                dataKey={line.dataKey}
                name={line.name}
                stroke={line.stroke}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

function EmptyBox({ loading }: { loading: boolean }) {
  return (
    <div className="perf-chart-empty">
      {loading ? <Spin description="等待数据..." /> : <Empty description="暂无实时数据" />}
    </div>
  );
}
