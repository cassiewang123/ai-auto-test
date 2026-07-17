import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Select,
  DatePicker,
  Button,
  Modal,
  Timeline,
  Statistic,
  Row,
  Col,
  Empty,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EyeOutlined,
  ReloadOutlined,
  FileSearchOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { uiTestRecordApi, projectApi, uiJunitApi } from '../services/api';
import type { Project, UiTestRecord } from '../types';

const { RangePicker } = DatePicker;

const statusConfig: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  passed: { color: 'green', text: '通过', icon: <CheckCircleOutlined /> },
  failed: { color: 'red', text: '失败', icon: <CloseCircleOutlined /> },
  error: { color: 'orange', text: '错误', icon: <ExclamationCircleOutlined /> },
};

export default function UiTestRecordsPage() {
  const [data, setData] = useState<UiTestRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [projects, setProjects] = useState<Project[]>([]);

  // 筛选
  const [filterProject, setFilterProject] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);

  // 统计
  const [stats, setStats] = useState({
    total: 0,
    passed: 0,
    passRate: 0,
    avgDuration: 0,
    lastTime: '-',
  });

  // 详情
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRecord, setDetailRecord] = useState<UiTestRecord | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // JUnit 导出
  const [exporting, setExporting] = useState<string | null>(null);

  async function loadData(
    p = page,
    ps = pageSize,
    projectId = filterProject,
    status = filterStatus,
    range = dateRange
  ) {
    setLoading(true);
    try {
      const res = await uiTestRecordApi.list({
        page: p,
        page_size: ps,
        project_id: projectId,
        status,
        start_date: range ? range[0].format('YYYY-MM-DD') : undefined,
        end_date: range ? range[1].format('YYYY-MM-DD') : undefined,
      });
      setData(res.data || []);
      setTotal(res.total);
      // 基于当前页数据计算统计
      computeStats(res.data || [], res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  function computeStats(records: UiTestRecord[], totalCount: number) {
    const passed = records.filter((r) => r.status === 'passed').length;
    const rate = records.length > 0 ? (passed / records.length) * 100 : 0;
    const avgDur =
      records.length > 0
        ? records.reduce((sum, r) => sum + (r.duration || 0), 0) / records.length
        : 0;
    const last = records
      .map((r) => r.executed_at)
      .sort()
      .pop();
    setStats({
      total: totalCount,
      passed,
      passRate: rate,
      avgDuration: avgDur,
      lastTime: last ? dayjs(last).format('YYYY-MM-DD HH:mm:ss') : '-',
    });
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

  async function showDetail(record: UiTestRecord) {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailRecord(record);
    try {
      const res = await uiTestRecordApi.get(record.id);
      if (res?.data) {
        setDetailRecord(res.data);
      }
    } catch (e: any) {
      // 详情接口失败时保留列表中的基础信息
    } finally {
      setDetailLoading(false);
    }
  }

  async function exportJunit(record: UiTestRecord) {
    setExporting(record.id);
    try {
      const xml = await uiJunitApi.getRecordJunit(record.id);
      // 创建 Blob 触发下载
      const blob = new Blob([xml], { type: 'application/xml' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `ui-record-${record.id}.xml`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success('JUnit XML 已导出');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setExporting(null);
    }
  }

  const columns: ColumnsType<UiTestRecord> = [
    { title: '用例标题', dataIndex: 'case_title', width: 200, ellipsis: true },
    {
      title: '项目',
      dataIndex: 'project_name',
      width: 120,
      render: (v: string) => v || '未分组',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => {
        const cfg = statusConfig[s] || { color: 'default', text: s };
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '耗时',
      dataIndex: 'duration',
      width: 90,
      render: (d: number) => `${(d || 0).toFixed(2)}s`,
    },
    {
      title: '步骤',
      width: 120,
      render: (_: any, r: UiTestRecord) =>
        `${r.passed_steps || 0}/${r.total_steps || 0}`,
    },
    {
      title: '执行时间',
      dataIndex: 'executed_at',
      width: 160,
      render: (t: string) =>
        t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '触发方式',
      dataIndex: 'triggered_by',
      width: 90,
    },
    {
      title: '操作',
      width: 200,
      render: (_: any, r: UiTestRecord) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => showDetail(r)}
          >
            详情
          </Button>
          <Button
            size="small"
            icon={<FileTextOutlined />}
            loading={exporting === r.id}
            onClick={() => exportJunit(r)}
          >
            导出 JUnit
          </Button>
        </Space>
      ),
    },
  ];

  function renderDetailContent() {
    if (!detailRecord) return <Empty description="暂无详情" />;
    const cfg = statusConfig[detailRecord.status] || {
      color: 'default',
      text: detailRecord.status,
    };
    return (
      <div>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic
                title="执行状态"
                value={cfg.text}
                styles={{ content: { fontWeight: 700 } }}
                prefix={cfg.icon}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic
                title="通过 / 总步骤"
                value={`${detailRecord.passed_steps || 0} / ${detailRecord.total_steps || 0}`}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic
                title="执行耗时"
                value={detailRecord.duration || 0}
                precision={2}
                suffix="s"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic
                title="浏览器"
                value={detailRecord.browser_type || '-'}
              />
            </Card>
          </Col>
        </Row>

        <div style={{ marginBottom: 16 }}>
          <p style={{ margin: '4px 0' }}>
            <strong>用例标题：</strong>
            {detailRecord.case_title}
          </p>
          <p style={{ margin: '4px 0' }}>
            <strong>所属项目：</strong>
            {detailRecord.project_name || '未分组'}
          </p>
          <p style={{ margin: '4px 0' }}>
            <strong>起始 URL：</strong>
            {detailRecord.url}
          </p>
          <p style={{ margin: '4px 0' }}>
            <strong>触发方式：</strong>
            {detailRecord.triggered_by}
          </p>
          <p style={{ margin: '4px 0' }}>
            <strong>执行时间：</strong>
            {detailRecord.executed_at
              ? dayjs(detailRecord.executed_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </p>
        </div>

        {detailRecord.error && (
          <div
            style={{
              background: '#fff2f0',
              border: '1px solid #ffccc7',
              borderRadius: 6,
              padding: '8px 12px',
              marginBottom: 16,
            }}
          >
            <span style={{ color: '#ff4d4f', fontWeight: 600 }}>错误信息: </span>
            <span style={{ color: '#5c0011' }}>{detailRecord.error}</span>
          </div>
        )}

        {detailRecord.step_results && detailRecord.step_results.length > 0 && (
          <Card size="small" title="步骤执行详情">
            <Timeline
              items={detailRecord.step_results.map((s: any, i: number) => ({
                key: i,
                color: s.status === 'passed' ? 'green' : 'red',
                dot:
                  s.status === 'passed' ? (
                    <CheckCircleOutlined style={{ fontSize: 16, color: '#52c41a' }} />
                  ) : (
                    <CloseCircleOutlined style={{ fontSize: 16, color: '#ff4d4f' }} />
                  ),
                children: (
                  <div>
                    <div style={{ fontWeight: 600 }}>
                      步骤 {s.step || i + 1}: {s.action}
                      {s.selector ? ` -> ${s.selector}` : ''}
                      {s.value ? ` = "${s.value}"` : ''}
                    </div>
                    {s.description && (
                      <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                        {s.description}
                      </div>
                    )}
                    {s.message && (
                      <div style={{ color: '#595959', fontSize: 12, marginTop: 2 }}>
                        {s.message}
                      </div>
                    )}
                    {s.error && (
                      <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 2 }}>
                        {s.error}
                      </div>
                    )}
                    <div style={{ color: '#bfbfbf', fontSize: 11, marginTop: 2 }}>
                      耗时: {s.duration}s
                    </div>
                  </div>
                ),
              }))}
            />
          </Card>
        )}
      </div>
    );
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <FileSearchOutlined />
            <span>UI 测试调用记录</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条记录
            </span>
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
            刷新
          </Button>
        }
      >
        {/* 统计卡片 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic title="总执行数" value={stats.total} />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic
                title="通过率"
                value={stats.passRate}
                precision={1}
                suffix="%"
                styles={{ content: { color: '#52c41a' } }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic
                title="平均耗时"
                value={stats.avgDuration}
                precision={2}
                suffix="s"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card size="small">
              <Statistic title="最近执行时间" value={stats.lastTime} />
            </Card>
          </Col>
        </Row>

        {/* 筛选栏 */}
        <Space style={{ marginBottom: 16 }} size="middle">
          <Select
            allowClear
            placeholder="选择项目"
            style={{ width: 220 }}
            showSearch
            optionFilterProp="label"
            value={filterProject}
            options={projects.map((p) => ({ label: p.name, value: p.id }))}
            onChange={(v) => {
              setFilterProject(v);
              setPage(1);
              loadData(1, pageSize, v, filterStatus, dateRange);
            }}
          />
          <Select
            allowClear
            placeholder="选择状态"
            style={{ width: 150 }}
            value={filterStatus}
            options={[
              { label: '通过', value: 'passed' },
              { label: '失败', value: 'failed' },
              { label: '错误', value: 'error' },
            ]}
            onChange={(v) => {
              setFilterStatus(v);
              setPage(1);
              loadData(1, pageSize, filterProject, v, dateRange);
            }}
          />
          <RangePicker
            value={dateRange}
            onChange={(dates) => {
              const range = dates as [dayjs.Dayjs, dayjs.Dayjs] | null;
              setDateRange(range);
              setPage(1);
              loadData(1, pageSize, filterProject, filterStatus, range);
            }}
          />
        </Space>

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
          columns={columns}
          size="middle"
          locale={{ emptyText: <Empty description="暂无调用记录" /> }}
        />
      </Card>

      {/* 详情 Modal */}
      <Modal
        title="调用记录详情"
        open={detailOpen}
        onCancel={() => {
          setDetailOpen(false);
          setDetailRecord(null);
        }}
        width={900}
        footer={
          <Button
            type="primary"
            onClick={() => {
              setDetailOpen(false);
              setDetailRecord(null);
            }}
          >
            关闭
          </Button>
        }
        destroyOnHidden
      >
        {detailLoading && !detailRecord ? (
          <div style={{ textAlign: 'center', padding: 60 }}>加载中...</div>
        ) : (
          renderDetailContent()
        )}
      </Modal>
    </div>
  );
}
