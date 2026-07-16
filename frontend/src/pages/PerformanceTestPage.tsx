import { useEffect, useState, useRef } from 'react';
import {
  Card,
  Table,
  Space,
  Button,
  Input,
  Select,
  Modal,
  Form,
  InputNumber,
  message,
  Popconfirm,
  Empty,
  Statistic,
  Descriptions,
  Row,
  Col,
  Spin,
  Badge,
  Tag,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { performanceTestApi, projectApi, testCaseApi } from '../services/api';
import type { Project, TestCase, PerfSla } from '../types';

const statusColor: Record<string, string> = {
  idle: 'default',
  running: 'processing',
  completed: 'green',
  failed: 'red',
};

const statusLabel: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

// 压测模式选项（功能14）
const modeOptions = [
  { label: '稳定负载（steady）', value: 'steady' },
  { label: '阶梯加压（ramp）', value: 'ramp' },
  { label: '峰值测试（peak）', value: 'peak' },
  { label: '自定义曲线（custom）', value: 'custom' },
];

const modeLabel: Record<string, string> = {
  steady: '稳定',
  ramp: '阶梯',
  peak: '峰值',
  custom: '自定义',
};

// SLA 状态徽章颜色（功能16）
const slaColor: Record<string, string> = {
  passed: 'green',
  failed: 'red',
  warning: 'gold',
};

const slaText: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  warning: '警告',
};

function pick(obj: any, keys: string[]): any {
  if (!obj) return undefined;
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  }
  return undefined;
}

function fmtMs(v: any): string {
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return `${n.toFixed(2)} ms`;
}

function fmtSec(v: any): string {
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return `${n.toFixed(2)} s`;
}

export default function PerformanceTestPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [projects, setProjects] = useState<Project[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [filterProject, setFilterProject] = useState<string | undefined>(undefined);

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const watchMode = Form.useWatch(['config', 'mode'], form);

  // 运行
  const [running, setRunning] = useState<string | null>(null);
  const [resultOpen, setResultOpen] = useState(false);
  const [runResult, setRunResult] = useState<any>(null);
  const [liveSnapshot, setLiveSnapshot] = useState<any>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function loadData(p = page, ps = pageSize, projectId = filterProject) {
    setLoading(true);
    try {
      const res = await performanceTestApi.list({
        page: p,
        page_size: ps,
        project_id: projectId,
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

  async function loadTestCases() {
    try {
      const res = await testCaseApi.list({ page: 1, page_size: 100 });
      setTestCases(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadData(1);
    loadProjects();
    loadTestCases();
    return () => {
      // 组件卸载时清理轮询定时器
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      config: {
        users: 10,
        spawn_rate: 5,
        duration: 60,
        ramp_up: 0,
        mode: 'steady',
        ramp_config: { start_users: 1, step: 5, stage_duration: 15, max_users: 20 },
        peak_config: { peak_users: 50, hold_duration: 30 },
        custom_config: { stages: [{ duration: 20, users: 10, spawn_rate: 5 }] },
        sla: { response_time_p95: 2000, error_rate: 0.05, rps_min: 10 },
      },
      case_ids: [],
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    const cfg = record.config || {};
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      project_id: record.project_id,
      case_ids: record.case_ids || [],
      config: {
        users: cfg.users ?? 10,
        spawn_rate: cfg.spawn_rate ?? 5,
        duration: cfg.duration ?? 60,
        ramp_up: cfg.ramp_up ?? 0,
        mode: cfg.mode ?? 'steady',
        ramp_config: cfg.ramp_config ?? {
          start_users: 1, step: 5, stage_duration: 15, max_users: 20,
        },
        peak_config: cfg.peak_config ?? { peak_users: 50, hold_duration: 30 },
        custom_config: cfg.custom_config ?? {
          stages: [{ duration: 20, users: 10, spawn_rate: 5 }],
        },
        sla: cfg.sla ?? { response_time_p95: 2000, error_rate: 0.05, rps_min: 10 },
      },
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const cfg = values.config || {};
      const mode = cfg.mode || 'steady';
      const config: any = {
        users: cfg.users ?? 10,
        spawn_rate: cfg.spawn_rate ?? 5,
        duration: cfg.duration ?? 60,
        ramp_up: cfg.ramp_up ?? 0,
        mode,
      };
      // 按模式附带专属配置
      if (mode === 'ramp') config.ramp_config = cfg.ramp_config || {};
      if (mode === 'peak') config.peak_config = cfg.peak_config || {};
      if (mode === 'custom') {
        config.custom_config = { stages: cfg.custom_config?.stages || [] };
      }
      // SLA 阈值（功能16）
      const sla: PerfSla = {};
      if (cfg.sla?.response_time_p95 != null) sla.response_time_p95 = Number(cfg.sla.response_time_p95);
      if (cfg.sla?.error_rate != null) sla.error_rate = Number(cfg.sla.error_rate);
      if (cfg.sla?.rps_min != null) sla.rps_min = Number(cfg.sla.rps_min);
      config.sla = sla;

      const payload: any = {
        name: values.name,
        description: values.description,
        project_id: values.project_id || null,
        case_ids: values.case_ids || [],
        config,
      };
      if (editing) {
        await performanceTestApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await performanceTestApi.create(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await performanceTestApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 后台执行 + 轮询实时进度（功能17 联动）
  async function handleRun(record: any) {
    setRunning(record.id);
    setRunResult(null);
    setLiveSnapshot(null);
    setResultOpen(true);
    try {
      await performanceTestApi.run(record.id);
      // 轮询 realtime 直到完成
      await new Promise<void>((resolve) => {
        pollTimerRef.current = setInterval(async () => {
          try {
            const rt = await performanceTestApi.getRealtime(record.id);
            const status = rt?.data?.status;
            setLiveSnapshot(rt?.data?.latest || null);
            if (status === 'completed' || status === 'failed') {
              if (pollTimerRef.current) {
                clearInterval(pollTimerRef.current);
                pollTimerRef.current = null;
              }
              resolve();
            }
          } catch {
            /* 忽略轮询错误 */
          }
        }, 2000);
      });
      // 获取最新结果
      const resultsRes = await performanceTestApi.getResults(record.id, {
        page: 1,
        page_size: 1,
      });
      setRunResult(resultsRes?.data?.[0] || null);
      message.success('压测执行完成');
      loadData();
      performanceTestApi.clearRealtime(record.id).catch(() => {});
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRunning(null);
    }
  }

  const columns = [
    { title: '场景名称', dataIndex: 'name', width: 180, ellipsis: true },
    {
      title: '关联用例数',
      dataIndex: 'case_ids',
      width: 90,
      align: 'center' as const,
      render: (ids: string[]) => (ids ? ids.length : 0),
    },
    {
      title: '压测模式',
      width: 90,
      align: 'center' as const,
      render: (_: any, record: any) => {
        const m = record.config?.mode || 'steady';
        return <Tag color="blue">{modeLabel[m] || m}</Tag>;
      },
    },
    {
      title: '并发用户数',
      width: 100,
      align: 'center' as const,
      render: (_: any, record: any) => record.config?.users ?? '-',
    },
    {
      title: '持续时间',
      width: 100,
      render: (_: any, record: any) => {
        const d = record.config?.duration;
        return d != null ? `${d} s` : '-';
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => (
        <Badge
          status={(statusColor[s] as any) || 'default'}
          text={statusLabel[s] || s || '-'}
        />
      ),
    },
    {
      title: '上次执行时间',
      dataIndex: 'last_run_at',
      width: 160,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      width: 250,
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<PlayCircleOutlined />}
            loading={running === record.id}
            onClick={() => handleRun(record)}
            data-testid="run-perf-btn"
          >
            运行
          </Button>
          <Popconfirm
            title="确认删除该压测场景？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 运行结果摘要数据（防御性取值）
  const r = runResult || {};
  const totalReq = Number(pick(r, ['total_requests'])) || 0;
  const successReq = Number(pick(r, ['success_requests'])) || 0;
  const failReq = Number(pick(r, ['fail_requests'])) || 0;
  const errorRate = Number(pick(r, ['error_rate'])) || 0;
  const avgRt = Number(pick(r, ['avg_response_time'])) || 0;
  const p50 = pick(r, ['p50']);
  const p90 = pick(r, ['p90']);
  const p95 = pick(r, ['p95']);
  const p99 = pick(r, ['p99']);
  const rps = Number(pick(r, ['rps'])) || 0;
  const duration = Number(pick(r, ['duration'])) || 0;
  const slaStatus = pick(r, ['sla_status']);
  const errorColor = errorRate >= 5 ? '#cf1322' : errorRate >= 1 ? '#d4b106' : '#3f8600';

  return (
    <div>
      <Card
        title={
          <Space>
            <ThunderboltOutlined />
            <span>压测场景</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个场景
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-testid="create-perf-btn">
              新建压测场景
            </Button>
          </Space>
        }
      >
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
              loadData(1, pageSize, v);
            }}
          />
        </Space>

        <Table
          dataSource={data}
          rowKey="id"
          loading={loading}
          data-testid="perf-tests-table"
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
          locale={{ emptyText: <Empty description="暂无压测场景" /> }}
        />
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑压测场景' : '新建压测场景'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={760}
        destroyOnClose
        data-testid={editing ? 'edit-modal' : 'create-modal'}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="场景名称"
            rules={[{ required: true, message: '请输入场景名称' }]}
          >
            <Input placeholder="如：登录接口压测" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input placeholder="场景描述（可选）" />
          </Form.Item>

          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              showSearch
              optionFilterProp="label"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>

          <Form.Item
            name="case_ids"
            label="关联用例"
            tooltip="选择要参与压测的 API 测试用例"
          >
            <Select
              mode="multiple"
              allowClear
              placeholder="选择 API 测试用例"
              showSearch
              optionFilterProp="label"
              options={testCases.map((c) => ({
                label: c.title,
                value: c.id,
              }))}
            />
          </Form.Item>

          <Card size="small" title="压测配置" style={{ marginBottom: 8 }}>
            <Form.Item
              name={['config', 'mode']}
              label="压测模式"
              tooltip="steady 稳定负载 / ramp 阶梯加压 / peak 峰值测试 / custom 自定义曲线"
            >
              <Select options={modeOptions} />
            </Form.Item>

            {/* steady / 通用基础参数 */}
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name={['config', 'users']}
                  label="并发用户数（steady/peak 基准）"
                  rules={[{ required: true, message: '请输入并发用户数' }]}
                >
                  <InputNumber min={1} max={1000} style={{ width: '100%' }} placeholder="10" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name={['config', 'spawn_rate']}
                  label="启动速率（每秒启动用户数）"
                  rules={[{ required: true, message: '请输入启动速率' }]}
                >
                  <InputNumber min={1} style={{ width: '100%' }} placeholder="5" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name={['config', 'duration']}
                  label="持续时间（秒）"
                  rules={[{ required: true, message: '请输入持续时间' }]}
                >
                  <InputNumber min={1} style={{ width: '100%' }} placeholder="60" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name={['config', 'ramp_up']} label="预热时间（秒）">
                  <InputNumber min={0} style={{ width: '100%' }} placeholder="0" />
                </Form.Item>
              </Col>
            </Row>

            {/* ramp 阶梯加压参数 */}
            {watchMode === 'ramp' && (
              <Row gutter={16}>
                <Col span={6}>
                  <Form.Item
                    name={['config', 'ramp_config', 'start_users']}
                    label="起始用户"
                  >
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item
                    name={['config', 'ramp_config', 'step']}
                    label="阶梯步长"
                  >
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item
                    name={['config', 'ramp_config', 'stage_duration']}
                    label="每阶段持续（秒）"
                  >
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item
                    name={['config', 'ramp_config', 'max_users']}
                    label="最大用户"
                  >
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            )}

            {/* peak 峰值测试参数 */}
            {watchMode === 'peak' && (
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    name={['config', 'peak_config', 'peak_users']}
                    label="峰值用户数"
                  >
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name={['config', 'peak_config', 'hold_duration']}
                    label="峰值保持时间（秒）"
                  >
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            )}

            {/* custom 自定义曲线：stages 动态表格 */}
            {watchMode === 'custom' && (
              <Form.List name={['config', 'custom_config', 'stages']}>
                {(fields, { add, remove }) => (
                  <>
                    {fields.map((field) => (
                      <Row key={field.key} gutter={8} align="middle">
                        <Col span={7}>
                          <Form.Item
                            {...field}
                            name={[field.name, 'duration']}
                            rules={[{ required: true, message: '必填' }]}
                            label="持续(秒)"
                          >
                            <InputNumber min={1} style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                        <Col span={7}>
                          <Form.Item
                            {...field}
                            name={[field.name, 'users']}
                            rules={[{ required: true, message: '必填' }]}
                            label="用户数"
                          >
                            <InputNumber min={0} style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                        <Col span={7}>
                          <Form.Item
                            {...field}
                            name={[field.name, 'spawn_rate']}
                            rules={[{ required: true, message: '必填' }]}
                            label="spawn_rate"
                          >
                            <InputNumber min={1} style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                        <Col span={3} style={{ textAlign: 'center' }}>
                          <MinusCircleOutlined
                            onClick={() => remove(field.name)}
                            style={{ color: '#dc2626' }}
                          />
                        </Col>
                      </Row>
                    ))}
                    <Button
                      type="dashed"
                      onClick={() => add({ duration: 20, users: 10, spawn_rate: 5 })}
                      icon={<PlusOutlined />}
                      style={{ width: '100%' }}
                    >
                      添加阶段
                    </Button>
                  </>
                )}
              </Form.List>
            )}
          </Card>

          {/* SLA 阈值区（功能16） */}
          <Card size="small" title="SLA 阈值（压测结束后自动评估）" style={{ marginBottom: 8 }}>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item
                  name={['config', 'sla', 'response_time_p95']}
                  label="P95 响应时间上限（ms）"
                >
                  <InputNumber min={0} style={{ width: '100%' }} placeholder="2000" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name={['config', 'sla', 'error_rate']}
                  label="错误率上限（0-1，如 0.05）"
                >
                  <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} placeholder="0.05" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name={['config', 'sla', 'rps_min']}
                  label="RPS 下限"
                >
                  <InputNumber min={0} style={{ width: '100%' }} placeholder="100" />
                </Form.Item>
              </Col>
            </Row>
          </Card>
        </Form>
      </Modal>

      {/* 运行结果 Modal（含实时进度） */}
      <Modal
        title="压测结果"
        open={resultOpen}
        onCancel={() => {
          if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setResultOpen(false);
          setRunResult(null);
          setLiveSnapshot(null);
        }}
        footer={
          <Button
            type="primary"
            onClick={() => {
              setResultOpen(false);
              setRunResult(null);
              setLiveSnapshot(null);
            }}
          >
            关闭
          </Button>
        }
        width={780}
        destroyOnClose
      >
        {running ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin tip="压测执行中..." />
            {liveSnapshot && (
              <Row gutter={16} style={{ marginTop: 24, textAlign: 'center' }}>
                <Col span={6}>
                  <Statistic title="当前用户数" value={liveSnapshot.active_users ?? 0} />
                </Col>
                <Col span={6}>
                  <Statistic title="瞬时 RPS" value={liveSnapshot.rps ?? 0} />
                </Col>
                <Col span={6}>
                  <Statistic title="总请求数" value={liveSnapshot.total_requests ?? 0} />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="错误率"
                    value={liveSnapshot.error_rate ?? 0}
                    precision={2}
                    suffix="%"
                    valueStyle={{ color: errorColor }}
                  />
                </Col>
              </Row>
            )}
          </div>
        ) : (
          <div>
            {slaStatus && (
              <div style={{ marginBottom: 16 }}>
                <Badge
                  status={(slaColor[slaStatus] as any) || 'default'}
                  text={<span style={{ fontWeight: 600 }}>SLA：{slaText[slaStatus] || slaStatus}</span>}
                />
              </div>
            )}
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="总请求数" value={totalReq} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="成功数"
                    value={successReq}
                    valueStyle={{ color: '#3f8600' }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="失败数"
                    value={failReq}
                    valueStyle={{ color: '#cf1322' }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="错误率"
                    value={errorRate}
                    precision={2}
                    suffix="%"
                    valueStyle={{ color: errorColor }}
                  />
                </Card>
              </Col>
            </Row>

            <Descriptions bordered size="small" column={2} labelStyle={{ width: 130 }}>
              <Descriptions.Item label="平均响应时间">{fmtMs(avgRt)}</Descriptions.Item>
              <Descriptions.Item label="P50">{fmtMs(p50)}</Descriptions.Item>
              <Descriptions.Item label="P90">{fmtMs(p90)}</Descriptions.Item>
              <Descriptions.Item label="P95">{fmtMs(p95)}</Descriptions.Item>
              <Descriptions.Item label="P99">{fmtMs(p99)}</Descriptions.Item>
              <Descriptions.Item label="RPS（每秒请求数）">{rps.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="持续时间" span={2}>{fmtSec(duration)}</Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  );
}
