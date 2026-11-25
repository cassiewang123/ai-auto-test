/**
 * 响应查看器：Body（pretty/raw + 复制）、Headers（复制）、Cookies 三个 Tab。
 *
 * 只负责展示 `ExecutionResultData['response']`，不参与请求流程。
 */
import { useMemo, useState } from 'react';
import { Button, Card, Empty, Segmented, Space, Table, Tabs, Tag, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import type { ExecutionResultData } from '../../services/api';
import {
  byteLength,
  formatByteSize,
  parseResponseCookies,
  renderResponseBody,
} from '../../utils/httpResponse';
import { copyTextToClipboard } from '../../utils/clipboard';

const CODE_COLOR: Record<string, string> = {
  '2xx': 'green',
  '3xx': 'blue',
  '4xx': 'orange',
  '5xx': 'red',
};

function statusCodeColor(statusCode: number): string {
  return CODE_COLOR[`${String(statusCode).charAt(0)}xx`] || 'default';
}

export interface ResponseViewerProps {
  response: NonNullable<ExecutionResultData['response']>;
}

export default function ResponseViewer({ response }: ResponseViewerProps) {
  const [bodyMode, setBodyMode] = useState<'pretty' | 'raw'>('pretty');

  const prettyText = useMemo(
    () => renderResponseBody(response.body, response.text),
    [response.body, response.text]
  );
  const rawText = useMemo(
    () => (response.text && response.text.length > 0 ? response.text : prettyText),
    [prettyText, response.text]
  );
  const headersText = useMemo(
    () => JSON.stringify(response.headers ?? {}, null, 2),
    [response.headers]
  );
  const cookies = useMemo(
    () => parseResponseCookies(response.headers),
    [response.headers]
  );

  const bodyText = bodyMode === 'pretty' ? prettyText : rawText;
  const bodySize = byteLength(bodyText);
  const headersSize = byteLength(headersText);

  async function copy(label: string, text: string) {
    try {
      await copyTextToClipboard(text);
      message.success(`${label}已复制`);
    } catch (error: any) {
      message.error(error?.message || '复制失败');
    }
  }

  return (
    <Card
      type="inner"
      style={{ marginBottom: 16 }}
      title={
        <Space size={8} wrap>
          <span>响应</span>
          <Tag color={statusCodeColor(response.status_code)} data-testid="response-status">
            {response.status_code}
          </Tag>
          <span style={{ color: '#6b7280', fontWeight: 400 }}>
            {response.elapsed.toFixed(4)}s
          </span>
          <Tag variant="filled" color="blue">
            {formatByteSize(bodySize)}
          </Tag>
        </Space>
      }
      extra={
        <Space size={8} wrap>
          <Segmented
            size="small"
            value={bodyMode}
            onChange={(value) => setBodyMode(value as 'pretty' | 'raw')}
            options={[
              { label: 'pretty', value: 'pretty' },
              { label: 'raw', value: 'raw' },
            ]}
            data-testid="response-body-mode"
          />
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => void copy('响应 Body', bodyText)}
            data-testid="copy-response-body"
          >
            复制 Body
          </Button>
        </Space>
      }
    >
      <Tabs
        size="small"
        items={[
          {
            key: 'body',
            label: 'Body',
            children: (
              <>
                <div className="quick-test-response-meta">
                  <span className="quick-test-editor-summary">
                    {bodyMode === 'pretty' ? '美化输出（JSON 缩进）' : '原始响应文本'} ·{' '}
                    {formatByteSize(bodySize)}
                  </span>
                </div>
                <pre
                  data-testid="response-body"
                  className="quick-test-response-pre"
                  style={{
                    background: '#1a1a2e',
                    color: '#e2e8f0',
                    padding: 16,
                    borderRadius: 8,
                    fontSize: 13,
                    lineHeight: 1.6,
                    margin: 0,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {bodyText || '(空)'}
                </pre>
              </>
            ),
          },
          {
            key: 'headers',
            label: 'Headers',
            children: (
              <>
                <div className="quick-test-response-meta">
                  <span className="quick-test-editor-summary">
                    {Object.keys(response.headers ?? {}).length} 个响应头 ·{' '}
                    {formatByteSize(headersSize)}
                  </span>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => void copy('响应 Headers', headersText)}
                    data-testid="copy-response-headers"
                  >
                    复制
                  </Button>
                </div>
                <pre
                  style={{
                    background: '#f9fafb',
                    padding: 12,
                    borderRadius: 6,
                    fontSize: 13,
                    margin: 0,
                    overflow: 'auto',
                  }}
                >
                  {headersText}
                </pre>
              </>
            ),
          },
          {
            key: 'cookies',
            label: `Cookies (${cookies.length})`,
            children:
              cookies.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="响应未返回 Set-Cookie"
                  style={{ margin: '24px 0' }}
                />
              ) : (
                <Table
                  dataSource={cookies}
                  rowKey={(record) => `${record.name}-${record.path ?? ''}-${record.domain ?? ''}`}
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: '名称',
                      dataIndex: 'name',
                      width: 150,
                      render: (value: string) => (
                        <code style={{ fontWeight: 600 }}>{value}</code>
                      ),
                    },
                    {
                      title: '值',
                      dataIndex: 'value',
                      ellipsis: true,
                      render: (value: string) => <code>{value || '(空)'}</code>,
                    },
                    {
                      title: 'Domain',
                      dataIndex: 'domain',
                      width: 150,
                      render: (value?: string) => value || '-',
                    },
                    {
                      title: 'Path',
                      dataIndex: 'path',
                      width: 100,
                      render: (value?: string) => value || '-',
                    },
                    {
                      title: 'Expires',
                      dataIndex: 'expires',
                      width: 190,
                      render: (value?: string) => value || '会话级',
                    },
                  ]}
                />
              ),
          },
        ]}
      />
    </Card>
  );
}
