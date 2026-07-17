import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  EyeOutlined,
  FileTextOutlined,
  HistoryOutlined,
  InfoCircleOutlined,
  PaperClipOutlined,
  ReloadOutlined,
  RetweetOutlined,
  StopOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { jobsApi } from '../services/api';
import type {
  Job,
  JobArtifact,
  JobEvent,
  JobEventPayload,
  JobStatus,
  JobStreamDoneMessage,
  JobStreamMessage,
  JobType,
} from '../types';

const { Text } = Typography;

const TERMINAL_STATUSES = new Set<JobStatus>(['succeeded', 'failed', 'cancelled', 'timed_out']);

const statusColorMap: Record<JobStatus, string> = {
  queued: 'blue',
  running: 'processing',
  succeeded: 'green',
  failed: 'red',
  cancelled: 'orange',
  timed_out: 'volcano',
};

const statusLabelMap: Record<JobStatus, string> = {
  queued: '排队中',
  running: '运行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  timed_out: '超时',
};

const jobTypeLabelMap: Record<JobType, string> = {
  api_case: 'API 用例',
  ui_case: 'UI 用例',
  ui_suite: 'UI 套件',
  performance: '性能测试',
};

const statusFilterOptions = Object.entries(statusLabelMap).map(([value, label]) => ({
  value,
  label,
}));

const typeFilterOptions = Object.entries(jobTypeLabelMap).map(([value, label]) => ({
  value,
  label,
}));

type StreamState = 'idle' | 'connecting' | 'live' | 'polling' | 'closed';
type ActionType = 'cancel' | 'retry';
type ExecutionEvidence = 'real' | 'placeholder' | 'in_progress' | 'not_started' | 'unknown';

interface ActionState {
  jobId: string;
  type: ActionType;
}

const executionEvidenceMeta: Record<
  ExecutionEvidence,
  { color: string; label: string; description: string }
> = {
  real: {
    color: 'green',
    label: '真实执行',
    description: '任务已有 Worker 执行记录，且未发现占位结果标记。',
  },
  placeholder: {
    color: 'warning',
    label: '占位执行',
    description: '后端结果或事件明确标记为占位执行，不能视为测试真实通过。',
  },
  in_progress: {
    color: 'processing',
    label: '执行中',
    description: '任务已由 Worker 接手，结束后将根据执行结果确认真实性。',
  },
  not_started: {
    color: 'default',
    label: '尚未执行',
    description: '任务尚无 Worker 开始执行的证据。',
  },
  unknown: {
    color: 'default',
    label: '证据待确认',
    description: '任务处于终态，但当前响应缺少足够的执行证据。',
  },
};

const streamStateMeta: Record<StreamState, { color: string; label: string }> = {
  idle: { color: 'default', label: '未连接' },
  connecting: { color: 'processing', label: '连接中' },
  live: { color: 'success', label: '实时连接' },
  polling: { color: 'warning', label: '轮询更新' },
  closed: { color: 'default', label: '任务已结束' },
};

const placeholderPattern = /(占位|placeholder|待(?:异步\s*)?runner|未(?:实际|真实)执行)/i;

function isTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

function renderStatusTag(status: JobStatus) {
  return <Tag color={statusColorMap[status]}>{statusLabelMap[status]}</Tag>;
}

function renderJobTypeTag(jobType: JobType) {
  return <Tag>{jobTypeLabelMap[jobType]}</Tag>;
}

function formatDateTime(value?: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

function formatDuration(job: Job): string {
  if (!job.started_at) {
    return job.status === 'queued' ? '等待中' : '-';
  }
  if (!job.finished_at) {
    return job.status === 'running' ? '运行中' : '-';
  }
  const milliseconds = Math.max(0, dayjs(job.finished_at).diff(dayjs(job.started_at)));
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(2)} s`;
  const minutes = Math.floor(milliseconds / 60_000);
  const seconds = Math.floor((milliseconds % 60_000) / 1000);
  return `${minutes} 分 ${seconds} 秒`;
}

function formatBytes(value?: number | null): string {
  if (value == null) return '-';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function parseEventPayload(payload?: JobEventPayload): unknown {
  if (payload == null || typeof payload !== 'string') return payload ?? null;
  try {
    return JSON.parse(payload) as unknown;
  } catch {
    return payload;
  }
}

function payloadToText(payload?: JobEventPayload): string {
  const parsed = parseEventPayload(payload);
  if (parsed == null) return '';
  if (typeof parsed === 'string') return parsed;
  return JSON.stringify(parsed, null, 2) ?? String(parsed);
}

function getEventSummary(event: JobEvent): string {
  const parsed = parseEventPayload(event.payload);
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const record = parsed as Record<string, unknown>;
    for (const key of ['message', 'error_message', 'error', 'status']) {
      if (typeof record[key] === 'string' && record[key]) {
        return String(record[key]);
      }
    }
  }
  return payloadToText(event.payload);
}

function getExecutionEvidence(job: Job, events: JobEvent[] = []): ExecutionEvidence {
  const evidenceText = [
    job.result_summary,
    job.error_message,
    ...events.map((event) => payloadToText(event.payload)),
  ]
    .filter(Boolean)
    .join('\n');

  if (placeholderPattern.test(evidenceText)) return 'placeholder';
  if (job.status === 'running') return 'in_progress';
  if (job.status === 'queued') return 'not_started';
  if (job.error_code === 'dispatch_failed') return 'not_started';
  if (job.started_at) return 'real';
  return 'unknown';
}

function renderExecutionEvidence(job: Job, events: JobEvent[] = []) {
  const evidence = getExecutionEvidence(job, events);
  const meta = executionEvidenceMeta[evidence];
  return (
    <Tooltip title={meta.description}>
      <Tag color={meta.color}>{meta.label}</Tag>
    </Tooltip>
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function eventColor(eventType: string): string {
  if (eventType.includes('failed')) return 'red';
  if (eventType.includes('cancelled')) return 'orange';
  if (eventType.includes('completed')) return 'green';
  if (eventType.includes('started')) return 'blue';
  return 'gray';
}

function isStreamDoneMessage(
  streamMessage: JobStreamMessage
): streamMessage is JobStreamDoneMessage {
  return streamMessage.event_type === 'done' && 'status' in streamMessage;
}

export default function JobsPage() {
  const [data, setData] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filterStatus, setFilterStatus] = useState<JobStatus | undefined>();
  const [filterType, setFilterType] = useState<JobType | undefined>();
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [actionState, setActionState] = useState<ActionState | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [artifacts, setArtifacts] = useState<JobArtifact[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<StreamState>('idle');

  const pageSizeRef = useRef(pageSize);
  const lastSequenceRef = useRef(0);
  const logContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    pageSizeRef.current = pageSize;
  }, [pageSize]);

  const loadData = useCallback(
    async (targetPage: number, targetPageSize: number, silent = false) => {
      if (!silent) setLoading(true);
      try {
        const response = await jobsApi.list({
          page: targetPage,
          page_size: targetPageSize,
          status: filterStatus,
          job_type: filterType,
        });
        setData(response.data || []);
        setTotal(response.total || 0);
      } catch (error) {
        if (!silent) {
          message.error(getErrorMessage(error, '加载任务列表失败'));
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [filterStatus, filterType]
  );

  useEffect(() => {
    setPage(1);
    void loadData(1, pageSizeRef.current);
  }, [filterStatus, filterType, loadData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => {
      void loadData(page, pageSize, true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadData, page, pageSize]);

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [events]);

  const mergeEvents = useCallback((incoming: JobEvent[]) => {
    if (incoming.length === 0) return;
    setEvents((current) => {
      const bySequence = new Map<number, JobEvent>();
      current.forEach((event) => bySequence.set(event.sequence, event));
      incoming.forEach((event) => bySequence.set(event.sequence, event));
      const merged = Array.from(bySequence.values()).sort(
        (left, right) => left.sequence - right.sequence
      );
      lastSequenceRef.current = merged.at(-1)?.sequence || 0;
      return merged;
    });
  }, []);

  const loadJobDetail = useCallback(
    async (job: Job, reset = false) => {
      if (reset) {
        setDetailLoading(true);
        setDetailError(null);
        setEvents([]);
        setArtifacts([]);
        lastSequenceRef.current = 0;
      }

      const [jobResult, eventResult, artifactResult] = await Promise.allSettled([
        jobsApi.get(job.id),
        jobsApi.getEvents(job.id, reset ? 0 : lastSequenceRef.current),
        jobsApi.getArtifacts(job.id),
      ]);

      const failures: string[] = [];
      if (jobResult.status === 'fulfilled') {
        setActiveJob((current) => (current?.id === job.id ? jobResult.value.data : current));
      } else {
        failures.push(getErrorMessage(jobResult.reason, '任务详情加载失败'));
      }

      if (eventResult.status === 'fulfilled') {
        mergeEvents(eventResult.value.data || []);
      } else {
        failures.push(getErrorMessage(eventResult.reason, '事件加载失败'));
      }

      if (artifactResult.status === 'fulfilled') {
        setArtifacts(artifactResult.value.data || []);
      } else {
        failures.push(getErrorMessage(artifactResult.reason, '产物加载失败'));
      }

      setDetailError(failures.length > 0 ? failures.join('；') : null);
      if (reset) setDetailLoading(false);
    },
    [mergeEvents]
  );

  const activeJobId = activeJob?.id;
  const activeJobStatus = activeJob?.status;

  useEffect(() => {
    if (!drawerOpen || !activeJobId || !activeJobStatus) return;
    if (isTerminal(activeJobStatus)) {
      setStreamState('closed');
      return;
    }

    const jobId = activeJobId;
    let disposed = false;
    let completed = false;
    let pollInFlight = false;
    let pollingTimer: number | undefined;
    let socket: WebSocket | undefined;

    const refreshIncrementally = async (finalRefresh = false) => {
      if (pollInFlight || disposed) return;
      pollInFlight = true;
      try {
        let shouldRefreshArtifacts = finalRefresh;
        const [eventResult, jobResult] = await Promise.allSettled([
          jobsApi.getEvents(jobId, lastSequenceRef.current),
          jobsApi.get(jobId),
        ]);
        if (disposed) return;

        if (eventResult.status === 'fulfilled') {
          mergeEvents(eventResult.value.data || []);
        }
        if (jobResult.status === 'fulfilled') {
          const latestJob = jobResult.value.data;
          setActiveJob((current) => (current?.id === jobId ? latestJob : current));
          setData((current) => current.map((item) => (item.id === jobId ? latestJob : item)));
          if (isTerminal(latestJob.status)) {
            completed = true;
            if (pollingTimer !== undefined) {
              window.clearInterval(pollingTimer);
            }
            setStreamState('closed');
            shouldRefreshArtifacts = true;
          }
        }
        if (shouldRefreshArtifacts) {
          try {
            const artifactResponse = await jobsApi.getArtifacts(jobId);
            if (!disposed) setArtifacts(artifactResponse.data || []);
          } catch {
            // 产物失败不改变已确认的任务终态，用户仍可手动刷新详情。
          }
        }
      } catch {
        if (!disposed) setStreamState('polling');
      } finally {
        pollInFlight = false;
      }
    };

    const startPolling = () => {
      if (disposed || completed || pollingTimer !== undefined) return;
      setStreamState('polling');
      void refreshIncrementally();
      pollingTimer = window.setInterval(() => {
        void refreshIncrementally();
      }, 2000);
    };

    const token = localStorage.getItem('access_token');
    if (!token || typeof window.WebSocket === 'undefined') {
      startPolling();
    } else {
      setStreamState('connecting');
      try {
        socket = new window.WebSocket(jobsApi.getStreamUrl(jobId, token));
        socket.onopen = () => {
          if (!disposed) setStreamState('live');
        };
        socket.onmessage = (event) => {
          if (disposed || typeof event.data !== 'string') return;
          try {
            const streamMessage = JSON.parse(event.data) as JobStreamMessage;
            if (isStreamDoneMessage(streamMessage)) {
              const finalStatus = streamMessage.status;
              completed = true;
              setStreamState('closed');
              if (finalStatus !== 'not_found') {
                setActiveJob((current) =>
                  current?.id === jobId ? { ...current, status: finalStatus } : current
                );
              }
              void refreshIncrementally(true);
              socket?.close();
              void loadData(page, pageSize, true);
              return;
            }
            mergeEvents([
              {
                ...streamMessage,
                job_id: jobId,
              },
            ]);
          } catch {
            startPolling();
            socket?.close();
          }
        };
        socket.onerror = () => {
          startPolling();
          socket?.close();
        };
        socket.onclose = () => {
          if (!disposed && !completed) startPolling();
        };
      } catch {
        startPolling();
      }
    }

    return () => {
      disposed = true;
      if (pollingTimer !== undefined) window.clearInterval(pollingTimer);
      socket?.close();
    };
  }, [activeJobId, activeJobStatus, drawerOpen, loadData, mergeEvents, page, pageSize]);

  const handleCancel = useCallback(
    async (job: Job) => {
      setActionState({ jobId: job.id, type: 'cancel' });
      try {
        const response = await jobsApi.cancel(job.id);
        const updatedJob = response.data;
        setData((current) => current.map((item) => (item.id === job.id ? updatedJob : item)));
        setActiveJob((current) => (current?.id === job.id ? updatedJob : current));
        message.success('任务取消请求已提交');
        void loadData(page, pageSize, true);
      } catch (error) {
        message.error(getErrorMessage(error, '取消任务失败'));
      } finally {
        setActionState(null);
      }
    },
    [loadData, page, pageSize]
  );

  const handleRetry = useCallback(
    async (job: Job) => {
      setActionState({ jobId: job.id, type: 'retry' });
      try {
        const response = await jobsApi.retry(job.id);
        message.success(`新任务已入队：${response.data.id}`);
        setPage(1);
        await loadData(1, pageSize, true);
      } catch (error) {
        message.error(getErrorMessage(error, '重试任务失败'));
      } finally {
        setActionState(null);
      }
    },
    [loadData, pageSize]
  );

  const handleViewDetail = useCallback(
    (job: Job) => {
      setActiveJob(job);
      setDrawerOpen(true);
      setStreamState('idle');
      void loadJobDetail(job, true);
    },
    [loadJobDetail]
  );

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setActiveJob(null);
    setEvents([]);
    setArtifacts([]);
    setDetailError(null);
    setStreamState('idle');
    lastSequenceRef.current = 0;
  }, []);

  const columns = useMemo<ColumnsType<Job>>(
    () => [
      {
        title: '任务 ID',
        dataIndex: 'id',
        key: 'id',
        width: 190,
        ellipsis: true,
        render: (id: string) => (
          <Tooltip title={id}>
            <Text copyable={{ text: id }} style={{ fontSize: 12 }}>
              {id.length > 18 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id}
            </Text>
          </Tooltip>
        ),
      },
      {
        title: '类型',
        dataIndex: 'job_type',
        key: 'job_type',
        width: 110,
        render: renderJobTypeTag,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: renderStatusTag,
      },
      {
        title: '执行真实性',
        key: 'execution_evidence',
        width: 120,
        render: (_: unknown, job: Job) => renderExecutionEvidence(job),
      },
      {
        title: '执行节点',
        dataIndex: 'assigned_worker_id',
        key: 'assigned_worker_id',
        width: 150,
        ellipsis: true,
        render: (worker?: string | null, job?: Job) => worker || job?.dispatch_queue || '-',
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: '耗时',
        key: 'duration',
        width: 100,
        render: (_: unknown, job: Job) => formatDuration(job),
      },
      {
        title: '结果摘要',
        dataIndex: 'result_summary',
        key: 'result_summary',
        width: 240,
        ellipsis: true,
        render: (summary?: string | null) => summary || '-',
      },
      {
        title: '操作',
        key: 'actions',
        width: 220,
        fixed: 'right',
        render: (_: unknown, job: Job) => {
          const canCancel = job.status === 'queued' || job.status === 'running';
          const canRetry =
            job.status === 'failed' || job.status === 'cancelled' || job.status === 'timed_out';
          return (
            <Space size={4}>
              <Button
                size="small"
                type="link"
                icon={<EyeOutlined />}
                onClick={() => handleViewDetail(job)}
                data-testid={`job-detail-${job.id}`}
              >
                详情
              </Button>
              <Button
                size="small"
                type="link"
                danger
                icon={<StopOutlined />}
                disabled={!canCancel}
                loading={actionState?.jobId === job.id && actionState.type === 'cancel'}
                onClick={() => void handleCancel(job)}
                data-testid={`job-cancel-${job.id}`}
              >
                取消
              </Button>
              <Button
                size="small"
                type="link"
                icon={<RetweetOutlined />}
                disabled={!canRetry}
                loading={actionState?.jobId === job.id && actionState.type === 'retry'}
                onClick={() => void handleRetry(job)}
                data-testid={`job-retry-${job.id}`}
              >
                重试
              </Button>
            </Space>
          );
        },
      },
    ],
    [actionState, handleCancel, handleRetry, handleViewDetail]
  );

  const artifactColumns = useMemo<ColumnsType<JobArtifact>>(
    () => [
      {
        title: '文件',
        dataIndex: 'filename',
        key: 'filename',
        ellipsis: true,
        render: (filename?: string | null, artifact?: JobArtifact) =>
          filename || artifact?.storage_key || artifact?.id || '-',
      },
      {
        title: '类型',
        dataIndex: 'artifact_type',
        key: 'artifact_type',
        width: 110,
        render: (type: string) => <Tag>{type}</Tag>,
      },
      {
        title: '大小',
        dataIndex: 'size_bytes',
        key: 'size_bytes',
        width: 100,
        render: formatBytes,
      },
      {
        title: '存储键',
        dataIndex: 'storage_key',
        key: 'storage_key',
        ellipsis: true,
        render: (storageKey?: string | null) =>
          storageKey ? (
            <Text copyable={{ text: storageKey }} style={{ fontSize: 12 }}>
              {storageKey}
            </Text>
          ) : (
            '-'
          ),
      },
      {
        title: '生成时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
        render: formatDateTime,
      },
    ],
    []
  );

  const activeEvidence = activeJob ? getExecutionEvidence(activeJob, events) : 'unknown';
  const activeEvidenceMeta = executionEvidenceMeta[activeEvidence];
  const activeStreamMeta = streamStateMeta[streamState];

  const detailTabs = activeJob
    ? [
        {
          key: 'overview',
          label: (
            <Space size={6}>
              <InfoCircleOutlined />
              概览
            </Space>
          ),
          children: (
            <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
              {activeEvidence === 'placeholder' && (
                <Alert
                  type="warning"
                  showIcon
                  title="该结果是占位执行"
                  description="任务状态即使显示成功，也不代表浏览器、套件或性能测试已真实运行。"
                  data-testid="placeholder-warning"
                />
              )}
              {detailError && <Alert type="warning" showIcon title={detailError} />}
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="任务 ID" span={2}>
                  <Text copyable={{ text: activeJob.id }}>{activeJob.id}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="任务类型">
                  {renderJobTypeTag(activeJob.job_type)}
                </Descriptions.Item>
                <Descriptions.Item label="任务状态">
                  {renderStatusTag(activeJob.status)}
                </Descriptions.Item>
                <Descriptions.Item label="执行真实性">
                  {renderExecutionEvidence(activeJob, events)}
                </Descriptions.Item>
                <Descriptions.Item label="实时通道">
                  <Tag color={activeStreamMeta.color}>{activeStreamMeta.label}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="关联资源">
                  {activeJob.resource_id ? (
                    <Text copyable={{ text: activeJob.resource_id }}>{activeJob.resource_id}</Text>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="项目 ID">
                  {activeJob.project_id ? (
                    <Text copyable={{ text: activeJob.project_id }}>{activeJob.project_id}</Text>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="创建者">{activeJob.created_by || '-'}</Descriptions.Item>
                <Descriptions.Item label="执行节点">
                  {activeJob.assigned_worker_id || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="调度模式">
                  {activeJob.dispatch_mode || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="调度队列">
                  {activeJob.dispatch_queue || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="排队时间">
                  {formatDateTime(activeJob.queued_at)}
                </Descriptions.Item>
                <Descriptions.Item label="开始时间">
                  {formatDateTime(activeJob.started_at)}
                </Descriptions.Item>
                <Descriptions.Item label="结束时间">
                  {formatDateTime(activeJob.finished_at)}
                </Descriptions.Item>
                <Descriptions.Item label="耗时">{formatDuration(activeJob)}</Descriptions.Item>
                <Descriptions.Item label="超时限制">{activeJob.timeout_seconds}s</Descriptions.Item>
                <Descriptions.Item label="Celery 任务">
                  {activeJob.celery_task_id ? (
                    <Text copyable={{ text: activeJob.celery_task_id }}>
                      {activeJob.celery_task_id}
                    </Text>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="结果摘要" span={2}>
                  <Text style={{ whiteSpace: 'pre-wrap' }}>{activeJob.result_summary || '-'}</Text>
                </Descriptions.Item>
              </Descriptions>
              {(activeJob.error_code || activeJob.error_message) && (
                <Alert
                  type="error"
                  showIcon
                  title={activeJob.error_code || '任务执行失败'}
                  description={
                    <Text style={{ whiteSpace: 'pre-wrap' }}>
                      {activeJob.error_message || '未返回错误详情'}
                    </Text>
                  }
                  data-testid="job-error"
                />
              )}
              {activeEvidence !== 'placeholder' && (
                <Alert
                  type={activeEvidence === 'real' ? 'success' : 'info'}
                  showIcon
                  title={activeEvidenceMeta.label}
                  description={activeEvidenceMeta.description}
                />
              )}
            </Space>
          ),
        },
        {
          key: 'logs',
          label: (
            <Space size={6}>
              <FileTextOutlined />
              实时日志
              <Tag>{events.length}</Tag>
            </Space>
          ),
          children: (
            <div
              data-testid="job-live-log"
              style={{
                border: '1px solid #30363d',
                borderRadius: 6,
                overflow: 'hidden',
                background: '#0d1117',
              }}
            >
              <div
                style={{
                  height: 40,
                  padding: '0 12px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  background: '#161b22',
                  borderBottom: '1px solid #30363d',
                }}
              >
                <Text style={{ color: '#c9d1d9' }}>任务事件日志</Text>
                <Tag color={activeStreamMeta.color}>{activeStreamMeta.label}</Tag>
              </div>
              <div
                ref={logContainerRef}
                style={{
                  height: 360,
                  overflow: 'auto',
                  padding: '6px 0',
                  fontFamily: "'Cascadia Code', 'Fira Code', Consolas, monospace",
                  fontSize: 12,
                  lineHeight: 1.6,
                }}
              >
                {events.length === 0 ? (
                  <div
                    style={{
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#8b949e',
                    }}
                  >
                    暂无日志
                  </div>
                ) : (
                  events.map((event) => (
                    <div
                      key={event.sequence}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '74px 120px minmax(0, 1fr)',
                        gap: 10,
                        padding: '5px 12px',
                        borderBottom: '1px solid #21262d',
                      }}
                    >
                      <span style={{ color: '#8b949e' }}>
                        {event.created_at
                          ? dayjs(event.created_at).format('HH:mm:ss')
                          : `#${event.sequence}`}
                      </span>
                      <span
                        style={{
                          color:
                            eventColor(event.event_type) === 'red'
                              ? '#f85149'
                              : eventColor(event.event_type) === 'green'
                                ? '#3fb950'
                                : eventColor(event.event_type) === 'orange'
                                  ? '#d29922'
                                  : '#58a6ff',
                          fontWeight: 600,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {event.event_type}
                      </span>
                      <span
                        style={{
                          color: '#c9d1d9',
                          whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere',
                        }}
                      >
                        {getEventSummary(event) || '-'}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ),
        },
        {
          key: 'events',
          label: (
            <Space size={6}>
              <HistoryOutlined />
              事件
            </Space>
          ),
          children:
            events.length === 0 ? (
              <Empty description="暂无事件" />
            ) : (
              <Timeline
                items={events.map((event) => ({
                  key: event.sequence,
                  color: eventColor(event.event_type),
                  children: (
                    <div>
                      <Space size="small" wrap>
                        <Tag>{event.event_type}</Tag>
                        <Text type="secondary">
                          {formatDateTime(event.created_at)} #{event.sequence}
                        </Text>
                      </Space>
                      {event.payload && (
                        <pre
                          style={{
                            margin: '8px 0 0',
                            padding: 10,
                            background: '#f6f8fa',
                            border: '1px solid #e5e7eb',
                            borderRadius: 4,
                            fontSize: 12,
                            maxHeight: 240,
                            overflow: 'auto',
                            whiteSpace: 'pre-wrap',
                            overflowWrap: 'anywhere',
                          }}
                        >
                          {payloadToText(event.payload)}
                        </pre>
                      )}
                    </div>
                  ),
                }))}
              />
            ),
        },
        {
          key: 'artifacts',
          label: (
            <Space size={6}>
              <PaperClipOutlined />
              产物
              <Tag>{artifacts.length}</Tag>
            </Space>
          ),
          children: (
            <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
              <Alert type="info" showIcon title="当前接口仅提供产物元数据，未返回可下载地址" />
              <Table<JobArtifact>
                rowKey="id"
                size="small"
                columns={artifactColumns}
                dataSource={artifacts}
                pagination={false}
                scroll={{ x: 720 }}
                locale={{ emptyText: <Empty description="暂无产物" /> }}
                data-testid="job-artifacts"
              />
            </Space>
          ),
        },
      ]
    : [];

  return (
    <div data-testid="jobs-page">
      <Card
        title={
          <Space>
            <span>任务中心</span>
            <Tag>{total}</Tag>
          </Space>
        }
        extra={
          <Space size="middle" wrap>
            <Select
              allowClear
              value={filterStatus}
              onChange={(value: JobStatus | undefined) => setFilterStatus(value)}
              options={statusFilterOptions}
              placeholder="全部状态"
              style={{ width: 130 }}
              data-testid="job-status-filter"
            />
            <Select
              allowClear
              value={filterType}
              onChange={(value: JobType | undefined) => setFilterType(value)}
              options={typeFilterOptions}
              placeholder="全部类型"
              style={{ width: 130 }}
              data-testid="job-type-filter"
            />
            <Space size={6}>
              <Text type="secondary">自动刷新</Text>
              <Switch checked={autoRefresh} onChange={setAutoRefresh} aria-label="自动刷新" />
            </Space>
            <Tooltip title="刷新任务列表">
              <Button
                icon={<ReloadOutlined />}
                onClick={() => void loadData(page, pageSize)}
                loading={loading}
                aria-label="刷新任务列表"
              />
            </Tooltip>
          </Space>
        }
      >
        <Table<Job>
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 1400 }}
          data-testid="jobs-table"
          locale={{ emptyText: <Empty description="暂无任务" /> }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (count) => `共 ${count} 条`,
            onChange: (nextPage, nextPageSize) => {
              const normalizedPage = nextPageSize !== pageSize ? 1 : nextPage;
              setPage(normalizedPage);
              setPageSize(nextPageSize);
              void loadData(normalizedPage, nextPageSize);
            },
          }}
        />
      </Card>

      <Drawer
        title={
          <Space>
            <span>任务详情</span>
            {activeJob && renderStatusTag(activeJob.status)}
            {activeJob && renderExecutionEvidence(activeJob, events)}
          </Space>
        }
        placement="right"
        size="min(780px, 100vw)"
        open={drawerOpen}
        onClose={closeDrawer}
        destroyOnHidden
      >
        {detailLoading ? (
          <div
            style={{
              minHeight: 280,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Spin description="加载任务详情" />
          </div>
        ) : activeJob ? (
          <Tabs defaultActiveKey="overview" items={detailTabs} />
        ) : (
          <Empty description="未选择任务" />
        )}
      </Drawer>
    </div>
  );
}
