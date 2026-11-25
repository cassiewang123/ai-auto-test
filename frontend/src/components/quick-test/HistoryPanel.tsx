/**
 * 接口调试页内嵌的历史调用面板。
 *
 * - 列表只取分页摘要（20 条），点击后才 `historyApi.get(id)` 拉详情回填，
 *   避免列表接口不带详情字段时回填出空表单。
 * - 刷新由父组件通过 refreshKey 递增触发（每次执行成功后 +1）。
 */
import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Empty, Space, Spin, Tag, Tooltip, message } from 'antd';
import { HistoryOutlined, ReloadOutlined } from '@ant-design/icons';
import { historyApi, type CallHistoryRecord } from '../../services/api';
import { formatRelativeTime } from '../../utils/httpResponse';

const PAGE_SIZE = 20;

const METHOD_COLOR: Record<string, string> = {
  GET: 'green',
  POST: 'orange',
  PUT: 'blue',
  PATCH: 'purple',
  DELETE: 'red',
  HEAD: 'cyan',
  OPTIONS: 'geekblue',
};

function statusCodeColor(statusCode: number | null | undefined): string {
  if (!statusCode) return 'default';
  if (statusCode < 300) return 'green';
  if (statusCode < 400) return 'blue';
  if (statusCode < 500) return 'orange';
  return 'red';
}

export interface HistoryPanelProps {
  /** 当前工作区项目，传入后只展示该项目的历史 */
  projectId?: string | null;
  /** 变化即触发一次重新加载 */
  refreshKey?: number;
  /** 详情加载完成后回填表单 */
  onRestore: (record: CallHistoryRecord) => void;
}

export default function HistoryPanel({
  projectId,
  refreshKey = 0,
  onRestore,
}: HistoryPanelProps) {
  const [items, setItems] = useState<CallHistoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await historyApi.list({
        page: 1,
        page_size: PAGE_SIZE,
        ...(projectId ? { project_id: projectId } : {}),
      });
      const list = (response?.data ?? []) as CallHistoryRecord[];
      setItems(list);
    } catch (loadError: any) {
      setItems([]);
      setError(loadError?.message || '历史记录加载失败');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  async function handleRestore(record: CallHistoryRecord) {
    setRestoringId(record.id);
    try {
      const response = await historyApi.get(record.id);
      if (!response?.data) {
        throw new Error('历史详情为空');
      }
      onRestore(response.data);
      message.success('已回填历史请求，点击「发送」即可重放');
    } catch (restoreError: any) {
      message.error(restoreError?.message || '历史详情加载失败');
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div className="quick-test-history-panel" data-testid="quick-test-history-panel">
      <div className="quick-test-history-header">
        <Space size={6}>
          <HistoryOutlined />
          <span>历史调用</span>
          {items.length > 0 && <Tag variant="filled">{items.length}</Tag>}
        </Space>
        <Tooltip title="刷新历史列表">
          <Button
            size="small"
            type="text"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void load()}
            aria-label="刷新历史列表"
            data-testid="history-refresh-btn"
          />
        </Tooltip>
      </div>

      <div className="quick-test-history-body">
        {error && (
          <Alert
            type="error"
            showIcon
            title="历史加载失败"
            description={error}
            action={
              <Button size="small" onClick={() => void load()}>
                重试
              </Button>
            }
          />
        )}

        {!error && loading && items.length === 0 && (
          <div className="quick-test-history-placeholder">
            <Spin size="small" /> <span>加载中…</span>
          </div>
        )}

        {!error && !loading && items.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无调用历史"
            style={{ margin: '24px 0' }}
          />
        )}

        {items.map((record) => (
          <button
            type="button"
            key={record.id}
            className="quick-test-history-item"
            onClick={() => void handleRestore(record)}
            disabled={restoringId === record.id}
            title={`${record.method} ${record.url}\n点击载入并回填表单`}
            data-testid="history-item"
          >
            <div className="quick-test-history-item-top">
              <Tag
                color={METHOD_COLOR[record.method] || 'default'}
                className="quick-test-history-method"
              >
                {record.method}
              </Tag>
              <span className="quick-test-history-url">{record.url}</span>
            </div>
            <div className="quick-test-history-item-meta">
              <Tag
                variant="filled"
                color={statusCodeColor(record.status_code)}
                className="quick-test-history-code"
              >
                {record.status_code ?? '—'}
              </Tag>
              <span>{Number(record.duration ?? 0).toFixed(3)}s</span>
              <span className="quick-test-history-time">
                {formatRelativeTime(record.executed_at)}
              </span>
              {restoringId === record.id && <Spin size="small" />}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
