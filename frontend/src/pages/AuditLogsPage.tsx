import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Select,
  Space,
  message,
  Card,
  DatePicker,
  Tag,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { PageResponse } from '../types';
import { apiClient } from '../services/api';
import dayjs, { type Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;

interface AuditLog {
  id: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  project_id: string | null;
  request_id: string | null;
  source_ip: string | null;
  user_agent: string | null;
  before: string | null;
  after: string | null;
  result: string;
  error_message: string | null;
  created_at: string | null;
}

const RESULT_COLOR: Record<string, string> = {
  success: 'green',
  failure: 'red',
  failed: 'red',
  error: 'red',
};

const ACTION_OPTIONS = [
  { label: '创建', value: 'create' },
  { label: '更新', value: 'update' },
  { label: '删除', value: 'delete' },
  { label: '执行', value: 'execute' },
  { label: '取消', value: 'cancel' },
  { label: '导出', value: 'export' },
  { label: '读取密钥', value: 'read_secret' },
];

const RESOURCE_OPTIONS = [
  { label: '用户', value: 'user' },
  { label: '角色', value: 'role' },
  { label: '项目', value: 'project' },
  { label: '测试用例', value: 'test_case' },
  { label: '测试计划', value: 'test_plan' },
  { label: '环境', value: 'environment' },
  { label: 'API Token', value: 'api_token' },
];

export default function AuditLogsPage() {
  const [data, setData] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [action, setAction] = useState<string | undefined>(undefined);
  const [resourceType, setResourceType] = useState<string | undefined>(undefined);
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);

  async function loadData(
    p = page,
    ps = pageSize,
    act = action,
    rt = resourceType,
    r = range
  ) {
    setLoading(true);
    try {
      const params: Record<string, any> = { page: p, page_size: ps };
      if (act) params.action = act;
      if (rt) params.resource_type = rt;
      if (r && r[0]) params.start_time = r[0].toISOString();
      if (r && r[1]) params.end_time = r[1].toISOString();
      const res = await apiClient.get<unknown, PageResponse<AuditLog>>(
        '/audit-logs',
        { params }
      );
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div data-testid="audit-logs-page">
      <Card
        title={
          <Space>
            <span>审计日志</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条
            </span>
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              allowClear
              placeholder="操作类型"
              style={{ width: 150 }}
              options={ACTION_OPTIONS}
              value={action}
              onChange={(v) => setAction(v)}
            />
            <Select
              allowClear
              placeholder="资源类型"
              style={{ width: 150 }}
              options={RESOURCE_OPTIONS}
              value={resourceType}
              onChange={(v) => setResourceType(v)}
            />
            <RangePicker
              showTime
              value={range as any}
              onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                setPage(1);
                loadData(1, pageSize, action, resourceType, range);
              }}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          data-testid="audit-logs-table"
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
          scroll={{ x: 1100 }}
          columns={[
            {
              title: '操作人',
              dataIndex: 'actor_name',
              width: 130,
              render: (v: string | null) => v || '-',
            },
            {
              title: '操作',
              dataIndex: 'action',
              width: 110,
              render: (v: string) => <Tag color="blue">{v}</Tag>,
            },
            {
              title: '资源类型',
              dataIndex: 'resource_type',
              width: 120,
            },
            {
              title: '资源 ID',
              dataIndex: 'resource_id',
              width: 160,
              ellipsis: true,
              render: (v: string | null) => v || '-',
            },
            {
              title: '结果',
              dataIndex: 'result',
              width: 100,
              render: (v: string) => (
                <Tag color={RESULT_COLOR[v] || 'default'}>{v}</Tag>
              ),
            },
            {
              title: '来源 IP',
              dataIndex: 'source_ip',
              width: 140,
              render: (v: string | null) => v || '-',
            },
            {
              title: '错误信息',
              dataIndex: 'error_message',
              ellipsis: true,
              render: (v: string | null) => v || '-',
            },
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 180,
              render: (t: string | null) =>
                t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
            },
          ]}
        />
      </Card>
    </div>
  );
}
