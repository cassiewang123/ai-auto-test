import { useEffect, useState } from 'react';
import {
  Card,
  Row,
  Col,
  Progress,
  Table,
  Tag,
  Select,
  Button,
  Space,
  Statistic,
  Empty,
  Spin,
  message,
  Tooltip,
  Typography,
} from 'antd';
import {
  ReloadOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PieChartOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { coverageApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';
import '../styles/report-workspace.css';

// 方法对应的标签颜色
const methodColor: Record<string, string> = {
  GET: 'green',
  POST: 'orange',
  PUT: 'blue',
  PATCH: 'purple',
  DELETE: 'red',
};

export default function CoveragePage() {
  const navigate = useNavigate();
  const { projects, selectedProjectId, setSelectedProjectId } = useWorkspace();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [coverageView, setCoverageView] = useState<'group' | 'method'>('group');
  const [coverageStatus, setCoverageStatus] = useState<'all' | 'uncovered' | 'covered'>(
    'uncovered'
  );

  async function loadCoverage() {
    setLoading(true);
    try {
      const res = await coverageApi.get(selectedProjectId ?? undefined);
      setData(res.data);
    } catch (e: any) {
      message.error(e.message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCoverage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  // 总覆盖率环形进度颜色
  const coverageRate = data?.coverage_rate ?? 0;
  const rateColor = coverageRate >= 80 ? '#52c41a' : coverageRate >= 50 ? '#faad14' : '#ff4d4f';

  // 方法分布柱状图最大值
  const methodMax = data?.by_method
    ? Math.max(...data.by_method.map((m: any) => m.total), 1)
    : 1;

  const coverageEntries = (
    coverageView === 'method'
      ? (data?.by_method || []).map((item: any) => ({
          ...item,
          key: `method-${item.method}`,
          label: item.method || 'UNKNOWN',
        }))
      : (data?.by_group || []).map((item: any) => ({
          ...item,
          key: `group-${item.group_path || '未分组'}`,
          label: item.group_path || '未分组',
        }))
  ).filter((item: any) => {
    if (coverageStatus === 'uncovered') return Number(item.uncovered) > 0;
    if (coverageStatus === 'covered') return Number(item.uncovered) === 0;
    return true;
  });

  function openApiList() {
    const query = selectedProjectId
      ? `?project_id=${encodeURIComponent(selectedProjectId)}`
      : '';
    navigate(`/api-list${query}`);
  }

  const coverageEntryColumns = [
    {
      title: coverageView === 'method' ? '请求方法' : '分组',
      dataIndex: 'label',
      ellipsis: true,
      render: (value: string) =>
        coverageView === 'method' ? (
          <Tag color={methodColor[value] || 'default'}>{value}</Tag>
        ) : (
          value
        ),
    },
    {
      title: '接口总数',
      dataIndex: 'total',
      width: 100,
      align: 'center' as const,
    },
    {
      title: '已覆盖',
      dataIndex: 'covered',
      width: 100,
      align: 'center' as const,
      render: (value: number) => (
        <span style={{ color: '#52c41a', fontWeight: 600 }}>{value}</span>
      ),
    },
    {
      title: '未覆盖',
      dataIndex: 'uncovered',
      width: 100,
      align: 'center' as const,
      render: (value: number) => (
        <span style={{ color: '#ff4d4f', fontWeight: 600 }}>{value}</span>
      ),
    },
    {
      title: '覆盖率',
      dataIndex: 'coverage_rate',
      width: 180,
      render: (value: number) => (
        <Progress
          percent={value}
          size="small"
          strokeColor={
            value >= 80 ? '#52c41a' : value >= 50 ? '#faad14' : '#ff4d4f'
          }
        />
      ),
    },
    {
      title: '操作',
      width: 130,
      render: () => (
        <Button type="link" icon={<ApiOutlined />} onClick={openApiList}>
          打开接口列表
        </Button>
      ),
    },
  ];

  const groupColumns = [
    {
      title: '分组',
      dataIndex: 'group_path',
      ellipsis: true,
      render: (v: string) => v || '未分组',
    },
    {
      title: '接口总数',
      dataIndex: 'total',
      width: 100,
      align: 'center' as const,
    },
    {
      title: '已覆盖',
      dataIndex: 'covered',
      width: 100,
      align: 'center' as const,
      render: (v: number) => <span style={{ color: '#52c41a', fontWeight: 600 }}>{v}</span>,
    },
    {
      title: '未覆盖',
      dataIndex: 'uncovered',
      width: 100,
      align: 'center' as const,
      render: (v: number) => <span style={{ color: '#ff4d4f', fontWeight: 600 }}>{v}</span>,
    },
    {
      title: '覆盖率',
      dataIndex: 'coverage_rate',
      width: 200,
      render: (v: number) => {
        const color = v >= 80 ? '#52c41a' : v >= 50 ? '#faad14' : '#ff4d4f';
        return (
          <Progress
            percent={v}
            size="small"
            strokeColor={color}
            format={(p) => `${p}%`}
          />
        );
      },
    },
  ];

  return (
    <div className="report-workspace">
      {/* 工具栏 */}
      <Card className="workspace-filter-card" style={{ marginBottom: 16 }}>
        <div className="workspace-filter-heading">
          <Space>
            <PieChartOutlined />
            <Typography.Text strong>覆盖率筛选</Typography.Text>
            <Tag color="green">项目服务端筛选</Tag>
          </Space>
          <Typography.Text type="secondary">
            项目通过 coverageApi.get(projectId) 查询；覆盖率按全部历史执行结果累计。
          </Typography.Text>
        </div>
        <div className="workspace-filter-grid">
          <div className="workspace-filter-item">
            <Typography.Text type="secondary">项目</Typography.Text>
            <Select
              value={selectedProjectId ?? undefined}
              onChange={(value) => setSelectedProjectId(value ?? null)}
              placeholder="全部项目"
              showSearch
              optionFilterProp="label"
              allowClear
              options={projects.map((project) => ({
                value: project.id,
                label: project.name,
              }))}
            />
          </div>
          <div className="workspace-filter-item">
            <Typography.Text type="secondary">缺口类型</Typography.Text>
            <Select
              value={coverageView}
              onChange={setCoverageView}
              options={[
                { value: 'group', label: '按分组' },
                { value: 'method', label: '按请求方法' },
              ]}
            />
          </div>
          <div className="workspace-filter-item">
            <Typography.Text type="secondary">覆盖状态</Typography.Text>
            <Select
              value={coverageStatus}
              onChange={setCoverageStatus}
              options={[
                { value: 'uncovered', label: '存在未覆盖' },
                { value: 'covered', label: '已全部覆盖' },
                { value: 'all', label: '全部' },
              ]}
            />
          </div>
          <Button icon={<ReloadOutlined />} onClick={loadCoverage} loading={loading}>
            刷新
          </Button>
        </div>
        <div className="workspace-filter-feedback">
          <Typography.Text type="secondary">
            缺口列表显示 {coverageEntries.length} 个
            {coverageView === 'group' ? '分组' : '请求方法'}聚合项；接口暂未返回单个未覆盖接口明细。
          </Typography.Text>
        </div>
      </Card>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin description="加载覆盖率数据..." />
        </div>
      ) : !data ? (
        <Card>
          <Empty description="暂无覆盖率数据" style={{ padding: 40 }} />
        </Card>
      ) : (
        <>
          {/* 顶部统计卡片 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="接口总数"
                  value={data.total_endpoints}
                  prefix={<ApiOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="已覆盖"
                  value={data.covered}
                  styles={{ content: { color: '#52c41a' } }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="未覆盖"
                  value={data.uncovered}
                  styles={{ content: { color: '#ff4d4f' } }}
                  prefix={<CloseCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="覆盖率"
                  value={data.coverage_rate}
                  precision={1}
                  suffix="%"
                  styles={{ content: { color: rateColor } }}
                  prefix={<PieChartOutlined />}
                />
              </Card>
            </Col>
          </Row>

          <Card
            title="未覆盖接口入口"
            extra={
              <Button icon={<ApiOutlined />} onClick={openApiList}>
                打开项目接口列表
              </Button>
            }
            style={{ marginBottom: 16 }}
          >
            <Table
              dataSource={coverageEntries}
              rowKey="key"
              columns={coverageEntryColumns}
              size="middle"
              scroll={{ x: 760 }}
              pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 项` }}
              locale={{
                emptyText: (
                  <Empty
                    description={
                      coverageStatus === 'uncovered'
                        ? '当前聚合维度下没有未覆盖项'
                        : '暂无覆盖率聚合数据'
                    }
                  />
                ),
              }}
            />
          </Card>

          <Row gutter={[16, 16]}>
            {/* 左侧：总覆盖率环形图 */}
            <Col xs={24} lg={10}>
              <Card title="总覆盖率" style={{ marginBottom: 16 }}>
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  <Progress
                    type="circle"
                    percent={data.coverage_rate}
                    size={200}
                    strokeColor={rateColor}
                    format={(p) => (
                      <div>
                        <div style={{ fontSize: 28, fontWeight: 700, color: rateColor }}>{p}%</div>
                        <div style={{ fontSize: 13, color: '#6b7280' }}>
                          {data.covered}/{data.total_endpoints} 接口
                        </div>
                      </div>
                    )}
                  />
                </div>
                <div style={{ textAlign: 'center', color: '#6b7280', fontSize: 13 }}>
                  共 {data.total_endpoints} 个接口，已覆盖 {data.covered} 个，未覆盖 {data.uncovered} 个
                </div>
              </Card>
            </Col>

            {/* 右侧：按方法分布柱状图 */}
            <Col xs={24} lg={14}>
              <Card title="按请求方法分布" style={{ marginBottom: 16 }}>
                {data.by_method && data.by_method.length > 0 ? (
                  data.by_method.map((m: any) => {
                    const barWidth = (m.total / methodMax) * 100;
                    const coveredWidth = m.total > 0 ? (m.covered / m.total) * barWidth : 0;
                    return (
                      <div key={m.method} style={{ marginBottom: 16 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Space>
                            <Tag color={methodColor[m.method] || 'default'} style={{ minWidth: 56, textAlign: 'center' }}>
                              {m.method}
                            </Tag>
                            <span style={{ fontSize: 13, color: '#6b7280' }}>
                              {m.covered}/{m.total} 已覆盖
                            </span>
                          </Space>
                          <span style={{ fontSize: 13, fontWeight: 600, color: m.coverage_rate >= 80 ? '#52c41a' : m.coverage_rate >= 50 ? '#faad14' : '#ff4d4f' }}>
                            {m.coverage_rate}%
                          </span>
                        </div>
                        <Tooltip title={`已覆盖 ${m.covered}，未覆盖 ${m.uncovered}`}>
                          <div style={{ background: '#f3f4f6', borderRadius: 6, height: 18, overflow: 'hidden', display: 'flex' }}>
                            <div style={{ width: `${coveredWidth}%`, background: '#52c41a', height: '100%', transition: 'width 0.3s' }} />
                            <div style={{ width: `${barWidth - coveredWidth}%`, background: '#ff4d4f', height: '100%', opacity: 0.5, transition: 'width 0.3s' }} />
                          </div>
                        </Tooltip>
                      </div>
                    );
                  })
                ) : (
                  <Empty description="暂无方法分布数据" />
                )}
              </Card>
            </Col>
          </Row>

          {/* 按分组的覆盖率表格 */}
          <Card title="按分组的覆盖率" style={{ marginBottom: 16 }}>
            <Table
              dataSource={data.by_group || []}
              rowKey="group_path"
              size="middle"
              pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 个分组` }}
              columns={groupColumns}
              scroll={{ x: 700 }}
              locale={{ emptyText: <Empty description="暂无分组数据" /> }}
            />
          </Card>

          {/* 最近执行趋势 */}
          {data.recent_runs && data.recent_runs.length > 0 && (
            <Card title="最近执行通过率趋势">
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '8px 0' }}>
                {data.recent_runs.map((r: any, idx: number) => {
                  const color = r.pass_rate >= 80 ? '#52c41a' : r.pass_rate >= 50 ? '#faad14' : '#ff4d4f';
                  return (
                    <Tooltip key={idx} title={`批次: ${r.run_id?.slice(0, 8)}\n总数: ${r.total}\n通过: ${r.passed}\n失败: ${r.failed}\n错误: ${r.error}`}>
                      <div style={{ minWidth: 100, textAlign: 'center', padding: '12px 8px', background: '#f9fafb', borderRadius: 8, border: '1px solid #f3f4f6' }}>
                        <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>{r.created_at}</div>
                        <div style={{ fontSize: 20, fontWeight: 700, color }}>{r.pass_rate}%</div>
                        <Progress percent={r.pass_rate} size="small" strokeColor={color} showInfo={false} style={{ marginTop: 4 }} />
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                          {r.passed}/{r.total}
                        </div>
                      </div>
                    </Tooltip>
                  );
                })}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
