import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Input,
  Select,
  DatePicker,
  Button,
  Space,
  Empty,
  Tooltip,
  message,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  FileTextOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { uiTestRecordApi, projectApi } from '../services/api';
import type { Project } from '../types';

const { RangePicker } = DatePicker;

// 日志级别配色
const levelConfig: Record<string, { color: string; text: string }> = {
  error: { color: 'red', text: 'ERROR' },
  warn: { color: 'orange', text: 'WARN' },
  info: { color: 'blue', text: 'INFO' },
  debug: { color: 'default', text: 'DEBUG' },
};

interface LogItem {
  id?: string;
  executed_at?: string;
  timestamp?: string;
  level?: string;
  case_title?: string;
  project_name?: string;
  message?: unknown;
  step_info?: unknown;
  case_id?: string;
  record_id?: string;
  [key: string]: any;
}

function formatLogValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export default function UiTestLogsPage() {
  const [data, setData] = useState<LogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [projects, setProjects] = useState<Project[]>([]);

  // 筛选
  const [keyword, setKeyword] = useState('');
  const [filterLevel, setFilterLevel] = useState<string | undefined>();
  const [filterProject, setFilterProject] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);

  async function loadData(
    p = page,
    ps = pageSize,
    kw = keyword,
    level = filterLevel,
    projectId = filterProject,
    range = dateRange
  ) {
    setLoading(true);
    try {
      const res = await uiTestRecordApi.searchLogs({
        page: p,
        page_size: ps,
        keyword: kw || undefined,
        level: level === 'all' ? undefined : level,
        project_id: projectId,
        start_date: range ? range[0].format('YYYY-MM-DD') : undefined,
        end_date: range ? range[1].format('YYYY-MM-DD') : undefined,
      });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadProjects() {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadData(1);
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: ColumnsType<LogItem> = [
    {
      title: '时间',
      dataIndex: 'executed_at',
      width: 170,
      render: (t: string, record) => {
        const timestamp = t || record.timestamp;
        return timestamp ? dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss') : '-';
      },
    },
    {
      title: '级别',
      dataIndex: 'level',
      width: 90,
      render: (lvl: string) => {
        const cfg = levelConfig[(lvl || '').toLowerCase()] || {
          color: 'default',
          text: (lvl || '-').toUpperCase(),
        };
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '用例标题',
      dataIndex: 'case_title',
      width: 180,
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '项目',
      dataIndex: 'project_name',
      width: 120,
      render: (v: string) => v || '未分组',
    },
    {
      title: '消息内容',
      dataIndex: 'message',
      ellipsis: true,
      render: (v: unknown) => {
        const text = formatLogValue(v);
        return text ? (
          <Tooltip title={text}>
            <span style={{ wordBreak: 'break-all' }}>{text}</span>
          </Tooltip>
        ) : (
          '-'
        );
      },
    },
    {
      title: '步骤信息',
      dataIndex: 'step_info',
      width: 150,
      ellipsis: true,
      render: (v: unknown) => {
        const text = formatLogValue(v);
        return text ? (
          <Tooltip title={text}>
            <code style={{ fontSize: 12 }}>{text}</code>
          </Tooltip>
        ) : (
          '-'
        );
      },
    },
    {
      title: '操作',
      width: 110,
      render: (_: any, r: LogItem) => {
        const id = r.record_id || r.id;
        return id ? (
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => viewRecord(id)}
          >
            关联记录
          </Button>
        ) : (
          '-'
        );
      },
    },
  ];

  async function viewRecord(id: string) {
    try {
      const res = await uiTestRecordApi.get(id);
      const record = res?.data;
      if (record) {
        message.info(
          `关联记录：${record.case_title} - 状态：${record.status} - 耗时：${(
            record.duration || 0
          ).toFixed(2)}s`
        );
      } else {
        message.info('未找到关联记录详情');
      }
    } catch (e: any) {
      message.error(e.message);
    }
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <FileTextOutlined />
            <span>UI 测试日志查询</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条日志
            </span>
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
            刷新
          </Button>
        }
      >
        {/* 筛选栏 */}
        <Space style={{ marginBottom: 16 }} size="middle" wrap>
          <Input
            placeholder="搜索关键词"
            allowClear
            style={{ width: 220 }}
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={() => {
              setPage(1);
              loadData(1, pageSize, keyword, filterLevel, filterProject, dateRange);
            }}
          />
          <Select
            allowClear
            placeholder="日志级别"
            style={{ width: 150 }}
            value={filterLevel}
            options={[
              { label: '全部', value: 'all' },
              { label: 'ERROR', value: 'error' },
              { label: 'WARN', value: 'warn' },
              { label: 'INFO', value: 'info' },
              { label: 'DEBUG', value: 'debug' },
            ]}
            onChange={(v) => {
              setFilterLevel(v);
              setPage(1);
              loadData(1, pageSize, keyword, v, filterProject, dateRange);
            }}
          />
          <Select
            allowClear
            placeholder="选择项目"
            style={{ width: 200 }}
            showSearch
            optionFilterProp="label"
            value={filterProject}
            options={projects.map((p) => ({ label: p.name, value: p.id }))}
            onChange={(v) => {
              setFilterProject(v);
              setPage(1);
              loadData(1, pageSize, keyword, filterLevel, v, dateRange);
            }}
          />
          <RangePicker
            value={dateRange}
            onChange={(dates) => {
              const range = dates as [dayjs.Dayjs, dayjs.Dayjs] | null;
              setDateRange(range);
              setPage(1);
              loadData(1, pageSize, keyword, filterLevel, filterProject, range);
            }}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => {
              setPage(1);
              loadData(1, pageSize, keyword, filterLevel, filterProject, dateRange);
            }}
          >
            查询
          </Button>
        </Space>

        <Table
          dataSource={data}
          rowKey={(record) => record.id || JSON.stringify(record)}
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
          columns={columns}
          size="middle"
          locale={{ emptyText: <Empty description="暂无日志记录" /> }}
        />
      </Card>
    </div>
  );
}
