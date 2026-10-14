/** 单次执行的完整结果视图：状态、响应、断言、提取变量、重试与脚本输出。 */
import { useState } from 'react';
import { Card, Space, Tag, Table, Tabs, Typography } from 'antd';
import type { ExecutionResultData } from '../services/api';

const statusColor: Record<string, string> = {
  passed: 'green',
  failed: 'red',
  error: 'orange',
  skipped: 'default',
};

const STATUS_LABEL: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  error: '错误',
  skipped: '跳过',
};

interface ExecutionResultViewProps {
  result: ExecutionResultData;
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '(空)';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre
      style={{
        background: '#f8fafc',
        border: '1px solid #e5e7eb',
        padding: 12,
        borderRadius: 6,
        fontSize: 12.5,
        lineHeight: 1.6,
        maxHeight: 320,
        overflow: 'auto',
        margin: 0,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
      }}
    >
      {children}
    </pre>
  );
}

export default function ExecutionResultView({ result }: ExecutionResultViewProps) {
  const [tab, setTab] = useState('body');
  const response = result.response;
  const assertions = result.assertion_results || [];
  const extracted = result.extracted_variables || [];
  const attempts = result.retry_attempts || [];

  return (
    <div>
      <Space wrap size={16} style={{ marginBottom: 12 }}>
        <Tag
          color={statusColor[result.status] || 'default'}
          style={{ fontSize: 14, padding: '3px 10px' }}
        >
          {STATUS_LABEL[result.status] || result.status}
        </Tag>
        <span style={{ color: '#4b5563' }}>
          耗时 <strong>{(result.duration ?? 0).toFixed(3)}s</strong>
        </span>
        {response && (
          <span style={{ color: '#4b5563' }}>
            HTTP 状态码 <strong>{response.status_code}</strong>
          </span>
        )}
        <span style={{ color: '#4b5563' }}>
          断言 <strong>{assertions.length}</strong> 条
          {assertions.length > 0 && (
            <>
              （通过 {assertions.filter((a) => a.passed).length} / 失败{' '}
              {assertions.filter((a) => !a.passed).length}）
            </>
          )}
        </span>
      </Space>

      {result.error_message && (
        <pre
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            padding: 12,
            borderRadius: 6,
            fontSize: 13,
            whiteSpace: 'pre-wrap',
            marginBottom: 16,
          }}
        >
          {result.error_message}
        </pre>
      )}

      {assertions.length > 0 && (
        <Card
          type="inner"
          title="断言结果"
          style={{ marginBottom: 16 }}
          styles={{ body: { padding: 0 } }}
        >
          <Table
            dataSource={assertions.map((item, index) => ({
              __rowKey: `assertion-${index}`,
              ...item,
            }))}
            rowKey="__rowKey"
            pagination={false}
            size="small"
            columns={[
              {
                title: '结果',
                dataIndex: 'passed',
                width: 70,
                render: (p: boolean) =>
                  p ? <Tag color="green">PASS</Tag> : <Tag color="red">FAIL</Tag>,
              },
              { title: '类型', dataIndex: 'assertion_type', width: 120 },
              {
                title: '表达式',
                dataIndex: 'expression',
                width: 150,
                render: (v: unknown) => (v ? <code>{String(v)}</code> : '-'),
              },
              { title: '操作符', dataIndex: 'operator', width: 90 },
              {
                title: '期望值',
                dataIndex: 'expected',
                width: 100,
                render: (v: unknown) => (v === null || v === undefined ? '-' : String(v)),
              },
              {
                title: '实际值',
                dataIndex: 'actual',
                width: 100,
                render: (v: unknown) => (v === null || v === undefined ? '-' : String(v)),
              },
              {
                title: '说明',
                dataIndex: 'message',
                render: (v: string) =>
                  v ? <span style={{ color: '#b45309' }}>{v}</span> : '-',
              },
            ]}
          />
        </Card>
      )}

      {response ? (
        <Card type="inner" title="响应内容" styles={{ body: { padding: 12 } }}>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={[
              {
                key: 'body',
                label: '响应体',
                children: (
                  <CodeBlock>
                    {typeof response.body === 'object' && response.body !== null
                      ? pretty(response.body)
                      : response.text || pretty(response.body)}
                  </CodeBlock>
                ),
              },
              {
                key: 'headers',
                label: `响应头 (${Object.keys(response.headers || {}).length})`,
                children: <CodeBlock>{pretty(response.headers)}</CodeBlock>,
              },
              {
                key: 'request',
                label: '实际请求',
                children: (
                  <div>
                    <Typography.Text type="secondary">
                      {result.request?.method} {result.request?.url}
                    </Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <CodeBlock>{pretty(result.request?.headers)}</CodeBlock>
                    </div>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      ) : (
        <Card type="inner">
          <Typography.Text type="secondary">本次执行没有收到响应</Typography.Text>
        </Card>
      )}

      {extracted.length > 0 && (
        <Card
          type="inner"
          title="提取的变量"
          style={{ marginTop: 16 }}
          styles={{ body: { padding: 0 } }}
        >
          <Table
            dataSource={extracted.map((item, index) => ({
              __rowKey: `extracted-${index}`,
              ...item,
            }))}
            rowKey="__rowKey"
            pagination={false}
            size="small"
            columns={[
              { title: '变量名', dataIndex: 'name', width: 180 },
              {
                title: '值',
                dataIndex: 'value',
                render: (v: unknown) => (
                  <code>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</code>
                ),
              },
              { title: '来源', dataIndex: 'source', width: 120 },
            ]}
          />
        </Card>
      )}

      {attempts.length > 1 && (
        <Card
          type="inner"
          title="重试记录"
          style={{ marginTop: 16 }}
          styles={{ body: { padding: 0 } }}
        >
          <Table
            dataSource={attempts.map((item, index) => ({
              __rowKey: `attempt-${index}`,
              ...item,
            }))}
            rowKey="__rowKey"
            pagination={false}
            size="small"
            columns={[
              { title: '第几次', dataIndex: 'attempt', width: 80 },
              {
                title: '状态',
                dataIndex: 'status',
                width: 90,
                render: (s: string) => (
                  <Tag color={statusColor[s] || 'default'}>{STATUS_LABEL[s] || s}</Tag>
                ),
              },
              {
                title: '状态码',
                dataIndex: 'status_code',
                width: 90,
                render: (c: number | null) => c ?? '-',
              },
              {
                title: '耗时(s)',
                dataIndex: 'duration',
                width: 90,
                render: (d: number) => (d ? d.toFixed(3) : '-'),
              },
              {
                title: '错误',
                dataIndex: 'error',
                render: (e: string) => (e ? <span style={{ color: '#b91c1c' }}>{e}</span> : '-'),
              },
            ]}
          />
        </Card>
      )}

      {(result.pre_script_result || result.post_script_result) && (
        <Card type="inner" title="脚本执行结果" style={{ marginTop: 16 }}>
          {result.pre_script_result && (
            <div style={{ marginBottom: 12 }}>
              <Space>
                <strong>前置脚本</strong>
                <Tag color={result.pre_script_result.success ? 'green' : 'red'}>
                  {result.pre_script_result.success ? '成功' : '失败'}
                </Tag>
              </Space>
              {result.pre_script_result.output && (
                <CodeBlock>{result.pre_script_result.output}</CodeBlock>
              )}
              {result.pre_script_result.error && (
                <CodeBlock>{result.pre_script_result.error}</CodeBlock>
              )}
            </div>
          )}
          {result.post_script_result && (
            <div>
              <Space>
                <strong>后置脚本</strong>
                <Tag color={result.post_script_result.success ? 'green' : 'red'}>
                  {result.post_script_result.success ? '成功' : '失败'}
                </Tag>
              </Space>
              {result.post_script_result.output && (
                <CodeBlock>{result.post_script_result.output}</CodeBlock>
              )}
              {result.post_script_result.error && (
                <CodeBlock>{result.post_script_result.error}</CodeBlock>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
