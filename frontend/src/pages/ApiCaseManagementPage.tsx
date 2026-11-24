import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  DeleteOutlined,
  DownloadOutlined,
  ReloadOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiCaseRecordApi } from '../services/api';

const { Text, Paragraph } = Typography;

type ApiCaseRecord = {
  id: string;
  title: string;
  method: string;
  url: string;
  headers?: Record<string, any>;
  params?: Record<string, any>;
  body?: any;
  assertions?: any[];
  case_type: string;
  priority: string;
  status: string;
  source?: string;
  description?: string | null;
  interface_name?: string | null;
  group_path?: string | null;
  created_at?: string;
};

const METHOD_COLOR: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'purple',
  DELETE: 'red',
};

const CASE_TYPE_LABEL: Record<string, string> = {
  normal: '正常',
  exception: '异常',
  boundary: '边界',
  permission: '权限',
};

const CASE_TYPE_COLOR: Record<string, string> = {
  normal: 'green',
  exception: 'volcano',
  boundary: 'gold',
  permission: 'purple',
};

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  active: '已确认',
  archived: '已归档',
};

export default function ApiCaseManagementPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ApiCaseRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [method, setMethod] = useState<string | undefined>();
  const [caseType, setCaseType] = useState<string | undefined>();
  const [priority, setPriority] = useState<string | undefined>();
  const [stats, setStats] = useState<Record<string, number>>({});
  const [detail, setDetail] = useState<ApiCaseRecord | null>(null);

  const loadData = useCallback(
    async (p = page, ps = pageSize) => {
      setLoading(true);
      try {
        const res = await apiCaseRecordApi.list({
          page: p,
          page_size: ps,
          keyword: keyword || undefined,
          method,
          case_type: caseType,
          priority,
        });
        setData(res.data || []);
        setTotal(res.total || 0);
      } catch (e: any) {
        message.error(e.message);
      } finally {
        setLoading(false);
      }
    },
    [keyword, method, caseType, page, pageSize, priority]
  );

  const loadStats = useCallback(async () => {
    try {
      const res = await apiCaseRecordApi.stats();
      setStats(res.data || {});
    } catch {
      // 统计失败不阻断列表
    }
  }, []);

  useEffect(() => {
    loadData(1, pageSize);
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [method, caseType, priority]);

  async function handleDelete(id: string) {
    try {
      await apiCaseRecordApi.remove(id);
      message.success('用例已删除');
      await Promise.all([loadData(), loadStats()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleExport() {
    const url = apiCaseRecordApi.exportUrl({
      keyword: keyword || undefined,
      method,
      case_type: caseType,
      priority,
    });
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`导出失败（HTTP ${response.status}）`);
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `接口用例-${new Date().toISOString().slice(0, 10)}.xlsx`;
      link.click();
      URL.revokeObjectURL(link.href);
      message.success(`已按当前筛选条件导出 ${total} 条用例`);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const columns = [
    {
      title: '用例标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (value: string, record: ApiCaseRecord) => (
        <a onClick={() => setDetail(record)}>{value}</a>
      ),
    },
    {
      title: '场景',
      dataIndex: 'case_type',
      width: 90,
      render: (value: string) => (
        <Tag color={CASE_TYPE_COLOR[value] || 'default'}>
          {CASE_TYPE_LABEL[value] || value}
        </Tag>
      ),
    },
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (value: string) => (
        <Tag color={METHOD_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    { title: 'URL', dataIndex: 'url', ellipsis: true, width: 280 },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={value === 'active' ? 'success' : 'default'}>
          {STATUS_LABEL[value] || value}
        </Tag>
      ),
    },
    {
      title: '关联接口',
      dataIndex: 'interface_name',
      width: 160,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => (value ? new Date(value).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, record: ApiCaseRecord) => (
        <Popconfirm title="确认删除该用例？" onConfirm={() => handleDelete(record.id)}>
          <Button type="link" size="small" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <UnorderedListOutlined />
            <span>用例管理</span>
            <Tag color="blue">接口用例库</Tag>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索用例标题"
              allowClear
              style={{ width: 200 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={() => loadData(1, pageSize)}
            />
            <Select
              allowClear
              placeholder="方法"
              style={{ width: 110 }}
              value={method}
              onChange={(value) => {
                setMethod(value);
                setPage(1);
              }}
              options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((v) => ({
                label: v,
                value: v,
              }))}
            />
            <Select
              allowClear
              placeholder="场景"
              style={{ width: 110 }}
              value={caseType}
              onChange={(value) => {
                setCaseType(value);
                setPage(1);
              }}
              options={Object.entries(CASE_TYPE_LABEL).map(([value, label]) => ({
                value,
                label,
              }))}
            />
            <Select
              allowClear
              placeholder="优先级"
              style={{ width: 110 }}
              value={priority}
              onChange={(value) => {
                setPriority(value);
                setPage(1);
              }}
              options={['P0', 'P1', 'P2', 'P3'].map((v) => ({ label: v, value: v }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleExport}>
              导出 Excel
            </Button>
            <Button type="primary" onClick={() => navigate('/api-case-generation')}>
              去生成用例
            </Button>
          </Space>
        }
      >
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[
            { label: '用例总数', value: stats.total || 0 },
            { label: '正常场景', value: stats.normal || 0 },
            { label: '异常场景', value: stats.exception || 0 },
            { label: '边界场景', value: stats.boundary || 0 },
            { label: 'P0 用例', value: stats.p0 || 0 },
          ].map((item) => (
            <Col key={item.label} xs={12} sm={8} md={4}>
              <Card size="small">
                <Statistic title={item.label} value={item.value} />
              </Card>
            </Col>
          ))}
        </Row>

        {data.length === 0 && !loading ? (
          <Empty
            description="还没有接口用例，点击右上角「去生成用例」按接口和传参生成"
            style={{ padding: 40 }}
          >
            <Button type="primary" onClick={() => navigate('/api-case-generation')}>
              去生成用例
            </Button>
          </Empty>
        ) : (
          <Table
            rowKey="id"
            loading={loading}
            dataSource={data}
            columns={columns}
            tableLayout="fixed"
            scroll={{ x: 1300 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              onChange: (p, ps) => {
                setPage(p);
                setPageSize(ps);
                loadData(p, ps);
              },
            }}
          />
        )}
      </Card>

      <Drawer
        title={detail?.title || '用例详情'}
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        width="min(760px, 92vw)"
      >
        {detail && (
          <>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="场景">
                <Tag color={CASE_TYPE_COLOR[detail.case_type]}>
                  {CASE_TYPE_LABEL[detail.case_type] || detail.case_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag>{detail.priority}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="方法">
                <Tag color={METHOD_COLOR[detail.method] || 'default'}>
                  {detail.method}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {STATUS_LABEL[detail.status] || detail.status}
              </Descriptions.Item>
              <Descriptions.Item label="URL" span={2}>
                <Text code>{detail.url}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="关联接口" span={2}>
                {detail.interface_name || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="分组" span={2}>
                {detail.group_path || '-'}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title="请求头" style={{ marginTop: 12 }}>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(detail.headers || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="查询参数" style={{ marginTop: 12 }}>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(detail.params || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="请求体" style={{ marginTop: 12 }}>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(detail.body ?? null, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="断言" style={{ marginTop: 12 }}>
              <Paragraph style={{ marginBottom: 0 }}>
                <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(detail.assertions || [], null, 2)}
                </pre>
              </Paragraph>
            </Card>
          </>
        )}
      </Drawer>
    </div>
  );
}
