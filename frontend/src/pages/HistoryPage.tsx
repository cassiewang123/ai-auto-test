import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  message,
  Popconfirm,
  Modal,
  Tabs,
  Statistic,
  Row,
  Col,
  Select,
  Input,
} from 'antd';
import {
  DeleteOutlined,
  ReloadOutlined,
  ClearOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import { historyApi } from '../services/api';
import type { CallHistoryRecord, HistoryStats } from '../services/api';
import dayjs from 'dayjs';

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
};
const statusColor: Record<string, string> = {
  passed: 'green', failed: 'red', error: 'orange',
};

export default function HistoryPage() {
  const [data, setData] = useState<CallHistoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterMethod, setFilterMethod] = useState<string>('');
  const [filterUrl, setFilterUrl] = useState('');

  // 详情 Modal
  const [detail, setDetail] = useState<CallHistoryRecord | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  async function loadData(p = page, ps = pageSize) {
    setLoading(true);
    try {
      const res = await historyApi.list({
        page: p,
        page_size: ps,
        status: filterStatus || undefined,
        method: filterMethod || undefined,
        url: filterUrl || undefined,
      });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadStats() {
    try {
      const res = await historyApi.stats();
      setStats(res.data);
    } catch {
      // 静默
    }
  }

  useEffect(() => {
    loadData(1);
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDelete(id: string) {
    try {
      await historyApi.delete(id);
      message.success('删除成功');
      loadData();
      loadStats();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleClear() {
    try {
      await historyApi.clear();
      message.success('已清空全部历史记录');
      loadData(1, pageSize);
      loadStats();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function openDetail(record: CallHistoryRecord) {
    try {
      const res = await historyApi.get(record.id);
      setDetail(res.data);
      setDetailOpen(true);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  return (
    <div>
      {/* 统计卡片 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总调用" value={stats.total} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="通过" value={stats.passed} valueStyle={{ color: '#059669' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="失败" value={stats.failed} valueStyle={{ color: '#dc2626' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="错误" value={stats.error} valueStyle={{ color: '#d97706' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="通过率" value={stats.pass_rate} suffix="%" />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="平均耗时" value={stats.avg_duration} suffix="s" />
            </Card>
          </Col>
        </Row>
      )}

      <Card
        title={
          <Space>
            <HistoryOutlined />
            <span>历史调用记录</span>
          </Space>
        }
        extra={
          <Space>
            <Popconfirm title="确认清空全部历史记录？此操作不可恢复" onConfirm={handleClear}>
              <Button danger icon={<ClearOutlined />}>清空全部</Button>
            </Popconfirm>
          </Space>
        }
      >
        {/* 筛选栏 */}
        <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
          <Select
            placeholder="按状态筛选"
            allowClear
            style={{ width: 140 }}
            value={filterStatus || undefined}
            onChange={(v) => setFilterStatus(v || '')}
            options={[
              { label: 'passed', value: 'passed' },
              { label: 'failed', value: 'failed' },
              { label: 'error', value: 'error' },
            ]}
          />
          <Select
            placeholder="按方法筛选"
            allowClear
            style={{ width: 120 }}
            value={filterMethod || undefined}
            onChange={(v) => setFilterMethod(v || '')}
            options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => ({ label: m, value: m }))}
          />
          <Input.Search
            placeholder="搜索 URL"
            allowClear
            style={{ width: 300 }}
            value={filterUrl}
            onChange={(e) => setFilterUrl(e.target.value)}
            onSearch={() => {
              setPage(1);
              loadData(1);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => { loadData(); loadStats(); }}>
            刷新
          </Button>
        </div>

        <Table
          dataSource={data}
          rowKey="id"
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
          onRow={(record) => ({
            onClick: () => openDetail(record),
            style: { cursor: 'pointer' },
          })}
          columns={[
            {
              title: '方法',
              dataIndex: 'method',
              width: 80,
              render: (m: string) => <Tag color={methodColor[m] || 'default'}>{m}</Tag>,
            },
            { title: 'URL', dataIndex: 'url', ellipsis: true },
            {
              title: '状态码',
              dataIndex: 'status_code',
              width: 80,
              render: (v: number | null) =>
                v ? (
                  <span style={{ color: v < 300 ? '#059669' : v < 400 ? '#d97706' : '#dc2626', fontWeight: 600 }}>
                    {v}
                  </span>
                ) : '-',
            },
            {
              title: '结果',
              dataIndex: 'status',
              width: 80,
              render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag>,
            },
            {
              title: '耗时',
              dataIndex: 'duration',
              width: 90,
              render: (d: number) => `${d.toFixed(3)}s`,
            },
            {
              title: '来源',
              dataIndex: 'source',
              width: 100,
              render: (s: string) => <Tag>{s}</Tag>,
            },
            {
              title: '文件',
              dataIndex: 'has_files',
              width: 50,
              render: (v: boolean) => (v ? <Tag color="purple">有</Tag> : '-'),
            },
            {
              title: '执行时间',
              dataIndex: 'executed_at',
              width: 170,
              render: (t: string) => dayjs(t).format('MM-DD HH:mm:ss'),
            },
            {
              title: '操作',
              width: 60,
              render: (_, record) => (
                <Popconfirm title="确认删除？" onConfirm={(e) => { e?.stopPropagation(); handleDelete(record.id); }}>
                  <Button size="small" danger icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()} />
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>

      {/* 详情 Modal */}
      <Modal
        title="调用详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={800}
      >
        {detail && (
          <div>
            <Space style={{ marginBottom: 16 }}>
              <Tag color={methodColor[detail.method] || 'default'}>{detail.method}</Tag>
              <Tag color={statusColor[detail.status] || 'default'}>{detail.status}</Tag>
              {detail.status_code && <Tag>{detail.status_code}</Tag>}
              <span style={{ color: '#6b7280' }}>{detail.duration.toFixed(3)}s</span>
              <span style={{ color: '#6b7280' }}>{dayjs(detail.executed_at).format('YYYY-MM-DD HH:mm:ss')}</span>
            </Space>

            <Tabs
              items={[
                {
                  key: 'request',
                  label: '请求',
                  children: (
                    <div>
                      <div style={{ marginBottom: 8 }}>
                        <label style={{ fontWeight: 600 }}>URL: </label>
                        <code style={{ background: '#f3f4f6', padding: '2px 6px', borderRadius: 4 }}>
                          {detail.url}
                        </code>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <label style={{ fontWeight: 600 }}>Headers:</label>
                        <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6, fontSize: 13 }}>
                          {JSON.stringify(detail.headers || {}, null, 2)}
                        </pre>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <label style={{ fontWeight: 600 }}>Params:</label>
                        <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6, fontSize: 13 }}>
                          {JSON.stringify(detail.params || {}, null, 2)}
                        </pre>
                      </div>
                      {detail.body && (
                        <div>
                          <label style={{ fontWeight: 600 }}>Body:</label>
                          <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6, fontSize: 13 }}>
                            {JSON.stringify(detail.body, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'response',
                  label: '响应',
                  children: (
                    <div>
                      {detail.response_headers && (
                        <div style={{ marginBottom: 8 }}>
                          <label style={{ fontWeight: 600 }}>Headers:</label>
                          <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6, fontSize: 13 }}>
                            {JSON.stringify(detail.response_headers, null, 2)}
                          </pre>
                        </div>
                      )}
                      <div>
                        <label style={{ fontWeight: 600 }}>Body:</label>
                        <pre style={{ background: '#1a1a2e', color: '#e2e8f0', padding: 16, borderRadius: 8, fontSize: 13, maxHeight: 400, overflow: 'auto' }}>
                          {typeof detail.response_body === 'object'
                            ? JSON.stringify(detail.response_body, null, 2)
                            : detail.response_text || '(空)'}
                        </pre>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'assertions',
                  label: `断言 (${detail.assertion_results?.length || 0})`,
                  children: (
                    <Table
                      dataSource={detail.assertion_results || []}
                      rowKey={(_, idx) => String(idx)}
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '结果', dataIndex: 'passed', width: 60,
                          render: (p: boolean) => p ? <Tag color="green">PASS</Tag> : <Tag color="red">FAIL</Tag> },
                        { title: '类型', dataIndex: 'assertion_type', width: 120 },
                        { title: '表达式', dataIndex: 'expression', render: (v: string) => v || '-' },
                        { title: '操作符', dataIndex: 'operator', width: 80 },
                        { title: '期望', dataIndex: 'expected', width: 80 },
                        { title: '实际', dataIndex: 'actual', width: 80 },
                      ]}
                    />
                  ),
                },
                {
                  key: 'pre-requests',
                  label: `前置条件 (${detail.pre_request_results?.length || 0})`,
                  children: detail.pre_request_results && detail.pre_request_results.length > 0 ? (
                    <Table
                      dataSource={detail.pre_request_results}
                      rowKey="index"
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '状态', dataIndex: 'success', width: 60,
                          render: (s: boolean) => s ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag> },
                        { title: '名称', dataIndex: 'name', width: 150 },
                        { title: '状态码', dataIndex: 'status_code', width: 80 },
                        { title: '耗时', dataIndex: 'elapsed', render: (v: number) => v ? `${v}s` : '-' },
                        { title: '错误', dataIndex: 'error', render: (v: string) => v || '-' },
                      ]}
                    />
                  ) : (
                    <span style={{ color: '#6b7280' }}>无前置条件</span>
                  ),
                },
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
