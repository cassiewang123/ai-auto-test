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

export default function PerfDashboardPage() {
  const [scenes, setScenes] = useState<any[]>([]);
  const [sceneId, setSceneId] = useState<string | undefined>(undefined);
  const [scenesLoading, setScenesLoading] = useState(false);

  // 实时数据
  const [realtime, setRealtime] = useState<any>(null);
  const [polling, setPolling] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 最近一次结果摘要（非运行中时展示）
  const [lastResult, setLastResult] = useState<any>(null);

  // 加载压测场景列表
  async function loadScenes() {
    setScenesLoading(true);
    try {
      const res = await performanceTestApi.list({ page: 1, page_size: 100 });
      const list = res.data || [];
      setScenes(list);
      // 默认选中第一个
      if (!sceneId && list.length > 0) {
        setSceneId(list[0].id);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setScenesLoading(false);
    }
  }

  // 拉取一次实时数据
  async function fetchRealtime(id: string) {
    try {
      const rt = await performanceTestApi.getRealtime(id);
      const data = rt?.data;
      setRealtime(data || null);
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
      setLastResult(res?.data?.[0] || null);
    } catch {
      setLastResult(null);
    }
  }

  useEffect(() => {
    loadScenes();
    return () => {
      // 组件卸载清理定时器
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 场景切换时停止轮询并拉取一次
  useEffect(() => {
    stopPolling();
    setRealtime(null);
    setLastResult(null);
    if (sceneId) {
      fetchRealtime(sceneId);
      fetchLastResult(sceneId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId]);

  // 启动轮询
  function startPolling() {
    if (!sceneId) {
      message.warning('请先选择压测场景');
      return;
    }
    stopPolling();
    setPolling(true);
    // 立即拉取一次
    fetchRealtime(sceneId);
    pollTimerRef.current = setInterval(async () => {
      const status = await fetchRealtime(sceneId);
      if (status === 'completed' || status === 'failed') {
        stopPolling();
        fetchLastResult(sceneId);
        if (status === 'completed') {
          message.success('压测已完成');
        } else {
          message.error('压测执行失败');
        }
      }
    }, 2000);
  }

  // 停止轮询
  function stopPolling() {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
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
    try {
      await performanceTestApi.run(sceneId);
      message.success('压测已启动');
      startPolling();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 清理实时内存
  async function handleClear() {
    if (!sceneId) return;
    try {
      await performanceTestApi.clearRealtime(sceneId);
      message.success('已清理实时数据');
      fetchRealtime(sceneId);
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
  const lrTotal = Number(r.total_requests ?? 0);
  const lrSuccess = Number(r.success_requests ?? 0);
  const lrFail = Number(r.fail_requests ?? 0);
  const lrErrRate = Number(r.error_rate ?? 0);
  const lrAvgRt = Number(r.avg_response_time ?? 0);
  const lrP95 = r.p95;
  const lrP99 = r.p99;
  const lrRps = Number(r.rps ?? 0);
  const lrDuration = Number(r.duration ?? 0);
  const lrSla = r.sla_status;
  const lrMode = r.mode || currentScene?.config?.mode;

  const isRunning = status === 'running';

  return (
    <div>
      <Card
        title={
          <Space>
            <DashboardOutlined />
            <span>压测实时仪表盘</span>
            <Badge
              status={(statusColor[status] as any) || 'default'}
              text={statusLabel[status] || status}
            />
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="选择压测场景"
              style={{ width: 280 }}
              value={sceneId}
              loading={scenesLoading}
              options={scenes.map((s) => ({
                label: `${s.name}${s.config?.mode ? `（${modeLabel[s.config.mode] || s.config.mode}）` : ''}`,
                value: s.id,
              }))}
              onChange={(v) => setSceneId(v)}
            />
            <Button icon={<ReloadOutlined />} onClick={loadScenes}>
              刷新场景
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
            ) : (
              <Button danger icon={<StopOutlined />} onClick={stopPolling}>
                停止轮询
              </Button>
            )}
            {polling && (
              <Tag color="processing" icon={<ThunderboltOutlined />}>
                轮询中（2s）
              </Tag>
            )}
          </Space>
        }
      >
        {!sceneId ? (
          <Empty description="请选择压测场景" />
        ) : (
          <>
            {/* 错误提示 */}
            {error && (
              <Alert
                style={{ marginBottom: 16 }}
                type="error"
                showIcon
                message="压测执行出错"
                description={error}
              />
            )}

            {/* 实时数字卡片 */}
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="当前用户数"
                    value={activeUsers}
                    prefix={<ThunderboltOutlined />}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic title="瞬时 RPS" value={instRps} precision={2} />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic title="总请求数" value={totalReq} />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="失败请求数"
                    value={failReq}
                    valueStyle={{ color: failReq > 0 ? '#cf1322' : '#3f8600' }}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="平均响应时间"
                    value={avgRt}
                    precision={2}
                    suffix="ms"
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="错误率"
                    value={errRate}
                    precision={2}
                    suffix="%"
                    valueStyle={{ color: errorRateColor(errRate) }}
                  />
                </Card>
              </Col>
            </Row>

            {/* 实时折线图区域 */}
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Card size="small" title="RPS（每秒请求数）趋势" styles={{ body: { height: 260 } }}>
                  {snapshots.length === 0 ? (
                    <EmptyBox loading={polling} />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={snapshots} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="t" name="时间" unit="s" fontSize={12} />
                        <YAxis fontSize={12} />
                        <Tooltip />
                        <Line type="monotone" dataKey="rps" name="RPS" stroke="#4f46e5" dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" title="平均响应时间趋势" styles={{ body: { height: 260 } }}>
                  {snapshots.length === 0 ? (
                    <EmptyBox loading={polling} />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={snapshots} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="t" name="时间" unit="s" fontSize={12} />
                        <YAxis fontSize={12} unit="ms" />
                        <Tooltip />
                        <Line type="monotone" dataKey="avg_rt" name="平均响应时间" stroke="#0891b2" dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </Card>
              </Col>
            </Row>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Card size="small" title="错误率趋势" styles={{ body: { height: 260 } }}>
                  {snapshots.length === 0 ? (
                    <EmptyBox loading={polling} />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={snapshots} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="t" name="时间" unit="s" fontSize={12} />
                        <YAxis fontSize={12} unit="%" />
                        <Tooltip />
                        <Line type="monotone" dataKey="error_rate" name="错误率" stroke="#dc2626" dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" title="活跃用户数趋势" styles={{ body: { height: 260 } }}>
                  {snapshots.length === 0 ? (
                    <EmptyBox loading={polling} />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={snapshots} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="t" name="时间" unit="s" fontSize={12} />
                        <YAxis fontSize={12} />
                        <Tooltip />
                        <Legend />
                        <Line type="stepAfter" dataKey="active_users" name="活跃用户" stroke="#059669" dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="total_requests" name="累计请求" stroke="#6366f1" dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </Card>
              </Col>
            </Row>

            {/* 最近一次结果摘要 */}
            <Card
              size="small"
              title={
                <Space>
                  <span>最近一次结果</span>
                  {lrSla && (
                    <Badge
                      status={lrSla === 'passed' ? 'success' : lrSla === 'failed' ? 'error' : 'warning'}
                      text={`SLA：${lrSla === 'passed' ? '通过' : lrSla === 'failed' ? '失败' : '警告'}`}
                    />
                  )}
                  {lrMode && <Tag color="blue">{modeLabel[lrMode] || lrMode}</Tag>}
                  {runId && <Tag>run_id: {runId.slice(0, 8)}…</Tag>}
                </Space>
              }
              extra={
                <Button size="small" onClick={handleClear}>
                  清理实时数据
                </Button>
              }
            >
              {lrTotal === 0 && !isRunning ? (
                <Empty description="暂无历史结果" />
              ) : (
                <Descriptions bordered size="small" column={4} labelStyle={{ width: 120 }}>
                  <Descriptions.Item label="总请求数">{lrTotal}</Descriptions.Item>
                  <Descriptions.Item label="成功数">
                    <span style={{ color: '#3f8600' }}>{lrSuccess}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="失败数">
                    <span style={{ color: '#cf1322' }}>{lrFail}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="错误率">
                    <span style={{ color: errorRateColor(lrErrRate) }}>{lrErrRate.toFixed(2)}%</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="平均响应时间">{fmtMs(lrAvgRt)}</Descriptions.Item>
                  <Descriptions.Item label="P95">{fmtMs(lrP95)}</Descriptions.Item>
                  <Descriptions.Item label="P99">{fmtMs(lrP99)}</Descriptions.Item>
                  <Descriptions.Item label="RPS">{lrRps.toFixed(2)}</Descriptions.Item>
                  <Descriptions.Item label="持续时间" span={2}>{fmtSec(lrDuration)}</Descriptions.Item>
                  <Descriptions.Item label="执行时间" span={2}>
                    {r.created_at ? dayjs(r.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Card>
          </>
        )}
      </Card>
    </div>
  );
}

// 空图表占位
function EmptyBox({ loading }: { loading: boolean }) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {loading ? <Spin tip="等待数据..." /> : <Empty description="暂无实时数据" />}
    </div>
  );
}
