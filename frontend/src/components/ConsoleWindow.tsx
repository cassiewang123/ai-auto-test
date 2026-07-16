import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Button, Tag, Space, Empty } from 'antd';
import {
  ClearOutlined,
  DownOutlined,
  ConsoleSqlOutlined,
} from '@ant-design/icons';

export interface ConsoleEntry {
  id: string;
  timestamp: string;
  type: 'request' | 'response' | 'pre-request' | 'assertion' | 'error' | 'info';
  method?: string;
  url?: string;
  statusCode?: number;
  status?: string;
  duration?: number;
  message?: string;
  detail?: any;
}

export interface ConsoleHandle {
  log: (entry: Omit<ConsoleEntry, 'id' | 'timestamp'>) => void;
  clear: () => void;
}

const typeColor: Record<string, string> = {
  request: '#2563eb',
  response: '#059669',
  'pre-request': '#0891b2',
  assertion: '#d97706',
  error: '#dc2626',
  info: '#6b7280',
};

const typeLabel: Record<string, string> = {
  request: 'REQUEST',
  response: 'RESPONSE',
  'pre-request': 'PRE-REQ',
  assertion: 'ASSERT',
  error: 'ERROR',
  info: 'INFO',
};

const ConsoleWindow = forwardRef<ConsoleHandle, { height?: number }>(
  ({ height = 300 }, ref) => {
    const [entries, setEntries] = useState<ConsoleEntry[]>([]);
    const [expanded, setExpanded] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const autoScrollRef = useRef(true);

    useImperativeHandle(ref, () => ({
      log(entry) {
        const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        setEntries((prev) => [...prev, { ...entry, id, timestamp: ts }]);
      },
      clear() {
        setEntries([]);
        setExpanded(null);
      },
    }));

    // 自动滚动到底部
    useEffect(() => {
      if (autoScrollRef.current && containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    }, [entries]);

    function handleScroll() {
      if (!containerRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 50;
    }

    function scrollToBottom() {
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
        autoScrollRef.current = true;
      }
    }

    const methodColor: Record<string, string> = {
      GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
    };

    return (
      <div
        style={{
          background: '#0d1117',
          borderRadius: 8,
          border: '1px solid #30363d',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          height,
        }}
      >
        {/* 标题栏 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 12px',
            background: '#161b22',
            borderBottom: '1px solid #30363d',
          }}
        >
          <Space size="small">
            <ConsoleSqlOutlined style={{ color: '#58a6ff' }} />
            <span style={{ color: '#c9d1d9', fontSize: 13, fontWeight: 600 }}>
              Console
            </span>
            <Tag style={{ fontSize: 11, margin: 0 }}>{entries.length} 条日志</Tag>
          </Space>
          <Space size="small">
            <Button
              size="small"
              type="text"
              icon={<DownOutlined />}
              onClick={scrollToBottom}
              style={{ color: '#8b949e' }}
            >
              底部
            </Button>
            <Button
              size="small"
              type="text"
              icon={<ClearOutlined />}
              onClick={() => setEntries([])}
              style={{ color: '#8b949e' }}
            >
              清空
            </Button>
          </Space>
        </div>

        {/* 日志列表 */}
        <div
          ref={containerRef}
          onScroll={handleScroll}
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '4px 0',
            fontFamily: "'Cascadia Code', 'Fira Code', Consolas, monospace",
            fontSize: 12.5,
            lineHeight: 1.6,
          }}
        >
          {entries.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center' }}>
              <Empty
                description={<span style={{ color: '#6e7681' }}>暂无日志，执行请求后将显示详细信息</span>}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          ) : (
            entries.map((entry) => (
              <div key={entry.id}>
                <div
                  onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
                  style={{
                    padding: '4px 12px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    borderBottom: expanded === entry.id ? '1px solid #21262d' : 'none',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#161b22')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <span style={{ color: '#6e7681', fontSize: 11, minWidth: 70 }}>
                    {entry.timestamp}
                  </span>
                  <span
                    style={{
                      color: typeColor[entry.type],
                      fontWeight: 700,
                      fontSize: 10,
                      minWidth: 56,
                    }}
                  >
                    {typeLabel[entry.type]}
                  </span>
                  {entry.method && (
                    <Tag
                      color={methodColor[entry.method] || 'default'}
                      style={{ fontSize: 10, margin: 0, minWidth: 44, textAlign: 'center' }}
                    >
                      {entry.method}
                    </Tag>
                  )}
                  {entry.statusCode !== undefined && entry.statusCode !== null && (
                    <span
                      style={{
                        color:
                          entry.statusCode < 300
                            ? '#3fb950'
                            : entry.statusCode < 400
                            ? '#d29922'
                            : '#f85149',
                        fontWeight: 600,
                        minWidth: 32,
                      }}
                    >
                      {entry.statusCode}
                    </span>
                  )}
                  {entry.status && (
                    <span
                      style={{
                        color:
                          entry.status === 'passed'
                            ? '#3fb950'
                            : entry.status === 'failed'
                            ? '#f85149'
                            : '#d29922',
                        fontWeight: 600,
                        fontSize: 11,
                      }}
                    >
                      [{entry.status}]
                    </span>
                  )}
                  <span style={{ color: '#c9d1d9', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.url || entry.message || ''}
                  </span>
                  {entry.duration !== undefined && (
                    <span style={{ color: '#6e7681', fontSize: 11 }}>
                      {entry.duration.toFixed(3)}s
                    </span>
                  )}
                </div>

                {/* 展开详情 */}
                {expanded === entry.id && entry.detail && (
                  <div
                    style={{
                      padding: '8px 12px 8px 80px',
                      background: '#0d1117',
                      borderBottom: '1px solid #21262d',
                    }}
                  >
                    <pre
                      style={{
                        color: '#c9d1d9',
                        fontSize: 12,
                        margin: 0,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                      }}
                    >
                      {typeof entry.detail === 'string'
                        ? entry.detail
                        : JSON.stringify(entry.detail, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    );
  }
);

ConsoleWindow.displayName = 'ConsoleWindow';
export default ConsoleWindow;
