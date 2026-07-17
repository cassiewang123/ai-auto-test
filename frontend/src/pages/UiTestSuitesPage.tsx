import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Input,
  Select,
  Modal,
  Form,
  message,
  Popconfirm,
  Empty,
  Statistic,
  Row,
  Col,
  Timeline,
  Switch,
  Radio,
  InputNumber,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  AppstoreOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  HistoryOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { uiTestSuiteApi, uiTestCaseApi, projectApi } from '../services/api';
import type { Project } from '../types';

export default function UiTestSuitesPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [projects, setProjects] = useState<Project[]>([]);
  const [filterProject, setFilterProject] = useState<string | undefined>();

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [form] = Form.useForm();

  // 可选用例列表
  const [allCases, setAllCases] = useState<any[]>([]);

  // 执行记录
  const [runsOpen, setRunsOpen] = useState(false);
  const [runs, setRuns] = useState<any[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runDetail, setRunDetail] = useState<any>(null);
  const [runDetailOpen, setRunDetailOpen] = useState(false);

  async function loadData(
    p = page,
    ps = pageSize,
    projectId = filterProject
  ) {
    setLoading(true);
    try {
      const res = await uiTestSuiteApi.list({
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

  async function loadAllCases() {
    try {
      // 拉取所有用例供套件选择
      const pageSize = 100;
      const firstPage = await uiTestCaseApi.list({ page: 1, page_size: pageSize });
      const cases = [...(firstPage.data || [])];
      const total = firstPage.total || cases.length;

      for (let currentPage = 2; cases.length < total; currentPage += 1) {
        const nextPage = await uiTestCaseApi.list({
          page: currentPage,
          page_size: pageSize,
        });
        const items = nextPage.data || [];
        if (items.length === 0) break;
        cases.push(...items);
      }

      setAllCases(cases);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadData(1);
    loadProjects();
    loadAllCases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      is_active: true,
      case_ids: [],
      execution_mode: 'sequential',
      max_workers: 4,
      retry_enabled: true,
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      project_id: record.project_id,
      case_ids: record.case_ids || [],
      is_active: record.is_active ?? true,
      execution_mode: record.execution_mode || 'sequential',
      max_workers: record.max_workers ?? 4,
      retry_enabled: record.retry_enabled ?? true,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload: any = {
        name: values.name,
        description: values.description,
        project_id: values.project_id || null,
        case_ids: values.case_ids || [],
        is_active: values.is_active ?? true,
        execution_mode: values.execution_mode || 'sequential',
        max_workers: values.execution_mode === 'parallel' ? values.max_workers ?? 4 : 4,
        retry_enabled: values.retry_enabled ?? true,
      };
      if (editing) {
        await uiTestSuiteApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await uiTestSuiteApi.create(payload);
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
      await uiTestSuiteApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleRun(record: any) {
    if (!record.case_ids || record.case_ids.length === 0) {
      message.warning('该套件未包含任何用例，请先编辑选择用例');
      return;
    }
    setRunning(record.id);
    try {
      const res = await uiTestSuiteApi.run(record.id);
      const result = res?.data;
      message.success(
        `套件执行完成：通过 ${result.passed}/${result.total}，失败 ${result.failed}`
      );
      loadData();
      // 展示本次执行详情
      if (result.run_id) {
        showRunDetail(result.run_id);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRunning(null);
    }
  }

  async function showRuns(record: any) {
    setRunsOpen(true);
    setRunsLoading(true);
    setRuns([]);
    try {
      const res = await uiTestSuiteApi.listRuns(record.id);
      setRuns(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRunsLoading(false);
    }
  }

  async function showRunDetail(runId: string) {
    setRunDetailOpen(true);
    setRunDetail(null);
    try {
      const res = await uiTestSuiteApi.getRun(runId);
      setRunDetail(res.data);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const columns: ColumnsType<any> = [
    { title: '套件名称', dataIndex: 'name', width: 200, ellipsis: true },
    {
      title: '项目',
      dataIndex: 'project_id',
      width: 140,
      render: (pid: string) => {
        const p = projects.find((x) => x.id === pid);
        return p ? p.name : '未分组';
      },
    },
    {
      title: '用例数',
      dataIndex: 'case_count',
      width: 90,
      align: 'center' as const,
    },
    {
      title: '执行模式',
      dataIndex: 'execution_mode',
      width: 110,
      render: (mode: string, record: any) =>
        mode === 'parallel' ? (
          <Tag color="purple" icon={<ThunderboltOutlined />}>
            并行 ×{record.max_workers || 4}
          </Tag>
        ) : (
          <Tag>顺序</Tag>
        ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      width: 320,
      render: (_: any, record: any) => (
        <Space wrap>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<PlayCircleOutlined />}
            loading={running === record.id}
            onClick={() => handleRun(record)}
          >
            执行
          </Button>
          <Button
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => showRuns(record)}
          >
            执行记录
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除该套件？"
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

  return (
    <div>
      <Card
        title={
          <Space>
            <AppstoreOutlined />
            <span>UI 测试套件</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个套件
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建套件
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
          locale={{ emptyText: <Empty description="暂无测试套件" /> }}
        />
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑测试套件' : '新建测试套件'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={680}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="套件名称"
            rules={[{ required: true, message: '请输入套件名称' }]}
          >
            <Input placeholder="如：登录模块回归套件" />
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
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="套件描述（可选）" rows={2} />
          </Form.Item>
          <Form.Item name="case_ids" label="选择用例">
            <Select
              mode="multiple"
              placeholder="选择要纳入套件的 UI 用例"
              showSearch
              optionFilterProp="label"
              options={allCases.map((c) => ({
                label: `${c.title} (${c.browser_type})`,
                value: c.id,
              }))}
              optionRender={(option) => (
                <Space>
                  <span>{option.label}</span>
                </Space>
              )}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item name="execution_mode" label="执行模式">
            <Radio.Group>
              <Radio value="sequential">顺序执行</Radio>
              <Radio value="parallel">并行执行</Radio>
            </Radio.Group>
          </Form.Item>
          {/* 选择并行执行时显示最大并发数配置 */}
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.execution_mode !== cur.execution_mode}
          >
            {({ getFieldValue }) =>
              getFieldValue('execution_mode') === 'parallel' ? (
                <Form.Item
                  name="max_workers"
                  label="最大并发数"
                  tooltip="并发数越大执行越快，但对服务器压力越大。建议 2-4 个。"
                  rules={[{ required: true, message: '请设置最大并发数' }]}
                >
                  <InputNumber min={1} max={10} style={{ width: 120 }} />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          {/* 启用失败重试：开启后套件内用例按各自重试配置自动重试 */}
          <Form.Item
            name="retry_enabled"
            label="启用失败重试"
            valuePropName="checked"
            tooltip="开启后，套件内的用例执行失败时将按各自的重试配置自动重试"
          >
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 执行记录列表 Modal */}
      <Modal
        title="套件执行记录"
        open={runsOpen}
        onCancel={() => setRunsOpen(false)}
        width={820}
        footer={
          <Button type="primary" onClick={() => setRunsOpen(false)}>
            关闭
          </Button>
        }
        destroyOnClose
      >
        <Table
          dataSource={runs}
          rowKey="id"
          loading={runsLoading}
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty description="暂无执行记录" /> }}
          columns={[
            {
              title: '执行时间',
              dataIndex: 'started_at',
              width: 160,
              render: (t: string) =>
                t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-',
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (s: string) => {
                const colorMap: Record<string, string> = {
                  completed: 'blue',
                  running: 'processing',
                  failed: 'red',
                };
                return <Tag color={colorMap[s] || 'default'}>{s}</Tag>;
              },
            },
            {
              title: '通过/总数',
              width: 110,
              render: (_: any, r: any) => (
                <span style={{ color: r.failed > 0 ? '#ff4d4f' : '#52c41a' }}>
                  {r.passed}/{r.total}
                </span>
              ),
            },
            {
              title: '失败',
              dataIndex: 'failed',
              width: 70,
              render: (v: number) =>
                v > 0 ? <Tag color="red">{v}</Tag> : <Tag color="green">0</Tag>,
            },
            {
              title: '耗时',
              dataIndex: 'duration',
              width: 90,
              render: (d: number) => `${(d || 0).toFixed(2)}s`,
            },
            {
              title: '操作',
              width: 100,
              render: (_: any, r: any) => (
                <Button
                  size="small"
                  onClick={() => showRunDetail(r.id)}
                >
                  详情
                </Button>
              ),
            },
          ]}
        />
      </Modal>

      {/* 执行详情 Modal */}
      <Modal
        title="套件执行详情"
        open={runDetailOpen}
        onCancel={() => {
          setRunDetailOpen(false);
          setRunDetail(null);
        }}
        width={860}
        footer={
          <Button
            type="primary"
            onClick={() => {
              setRunDetailOpen(false);
              setRunDetail(null);
            }}
          >
            关闭
          </Button>
        }
        destroyOnClose
      >
        {runDetail ? (
          <div>
            {/* 执行模式与加速比信息条 */}
            <div
              style={{
                marginBottom: 16,
                display: 'flex',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <span style={{ fontWeight: 600 }}>执行模式：</span>
              {runDetail.execution_mode === 'parallel' ? (
                <Tag color="purple" icon={<ThunderboltOutlined />}>
                  并行（并发 {runDetail.max_workers || 1}）
                </Tag>
              ) : (
                <Tag>顺序</Tag>
              )}
              {runDetail.execution_mode === 'parallel' &&
                runDetail.parallel_duration &&
                runDetail.duration > 0 && (
                  <Tag color="green" icon={<ThunderboltOutlined />}>
                    并行加速比：
                    {(runDetail.parallel_duration / runDetail.duration).toFixed(2)}
                    x（串行预估 {runDetail.parallel_duration.toFixed(2)}s / 实际{' '}
                    {runDetail.duration.toFixed(2)}s）
                  </Tag>
                )}
            </div>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="总用例数" value={runDetail.total} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="通过"
                    value={runDetail.passed}
                    valueStyle={{ color: '#52c41a' }}
                    prefix={<CheckCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="失败"
                    value={runDetail.failed}
                    valueStyle={{ color: runDetail.failed > 0 ? '#ff4d4f' : '#52c41a' }}
                    prefix={<CloseCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="总耗时"
                    value={runDetail.duration || 0}
                    precision={2}
                    suffix="s"
                  />
                </Card>
              </Col>
            </Row>
            {/* 重试统计卡片：展示总重试次数和重试过的用例 */}
            {runDetail.retry_enabled && (runDetail.total_retries || 0) > 0 && (
              <Card
                size="small"
                title={
                  <Space>
                    <ReloadOutlined style={{ color: '#4f46e5' }} />
                    <span>重试统计</span>
                  </Space>
                }
                style={{ marginBottom: 16 }}
              >
                <Row gutter={16}>
                  <Col span={6}>
                    <Statistic
                      title="总重试次数"
                      value={runDetail.total_retries || 0}
                      valueStyle={{ color: '#4f46e5' }}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title="重试用例数"
                      value={(runDetail.retried_cases || []).length}
                    />
                  </Col>
                  <Col span={12}>
                    <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
                      重试过的用例：
                    </div>
                    <Space wrap>
                      {(runDetail.retried_cases || []).map(
                        (rc: any, i: number) => (
                          <Tag
                            key={i}
                            color={rc.final_status === 'passed' ? 'green' : 'red'}
                          >
                            {rc.case_title}（{rc.attempts} 次）
                          </Tag>
                        )
                      )}
                    </Space>
                  </Col>
                </Row>
              </Card>
            )}
            {/* 并行模式下的甘特图时间线，直观展示用例并行执行情况 */}
            {runDetail.execution_mode === 'parallel' &&
              (runDetail.records || []).length > 0 && (
                <Card size="small" title="并行执行时间线" style={{ marginBottom: 16 }}>
                  {(() => {
                    const suiteStart = dayjs(runDetail.started_at);
                    const totalDur = runDetail.duration || 1;
                    const records = [...(runDetail.records || [])].sort(
                      (a, b) =>
                        dayjs(a.executed_at).valueOf() -
                        dayjs(b.executed_at).valueOf()
                    );
                    return (
                      <div>
                        {/* 时间轴刻度 */}
                        <div
                          style={{
                            display: 'flex',
                            marginLeft: 168,
                            marginRight: 68,
                            justifyContent: 'space-between',
                            fontSize: 11,
                            color: '#8c8c8c',
                            marginBottom: 4,
                          }}
                        >
                          <span>0s</span>
                          <span>{(totalDur / 2).toFixed(1)}s</span>
                          <span>{totalDur.toFixed(1)}s</span>
                        </div>
                        {records.map((r: any, i: number) => {
                          const offset =
                            suiteStart.isValid() && r.executed_at
                              ? dayjs(r.executed_at).diff(suiteStart, 'second', true)
                              : 0;
                          const leftPct = Math.max(
                            0,
                            Math.min(100, (offset / totalDur) * 100)
                          );
                          const widthPct = Math.max(
                            2,
                            Math.min(100 - leftPct, (r.duration / totalDur) * 100)
                          );
                          return (
                            <div
                              key={i}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                marginBottom: 6,
                              }}
                            >
                              <div
                                style={{
                                  width: 160,
                                  textAlign: 'right',
                                  paddingRight: 8,
                                  fontSize: 12,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={r.case_title}
                              >
                                {r.case_title}
                              </div>
                              <div
                                style={{
                                  flex: 1,
                                  position: 'relative',
                                  height: 18,
                                  background: '#f5f5f5',
                                  borderRadius: 4,
                                }}
                              >
                                <Tooltip
                                  title={`开始: +${offset.toFixed(2)}s · 耗时: ${(
                                    r.duration || 0
                                  ).toFixed(2)}s · ${r.status}`}
                                >
                                  <div
                                    style={{
                                      position: 'absolute',
                                      left: `${leftPct}%`,
                                      width: `${widthPct}%`,
                                      height: '100%',
                                      background:
                                        r.status === 'passed' ? '#52c41a' : '#ff4d4f',
                                      borderRadius: 4,
                                      opacity: 0.85,
                                    }}
                                  />
                                </Tooltip>
                              </div>
                              <div
                                style={{
                                  width: 60,
                                  paddingLeft: 8,
                                  fontSize: 12,
                                  color: '#8c8c8c',
                                }}
                              >
                                {(r.duration || 0).toFixed(2)}s
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </Card>
              )}
            <Card size="small" title="用例执行明细">
              <Timeline
                items={(runDetail.records || []).map((r: any, i: number) => ({
                  key: i,
                  color: r.status === 'passed' ? 'green' : 'red',
                  dot:
                    r.status === 'passed' ? (
                      <CheckCircleOutlined style={{ fontSize: 16, color: '#52c41a' }} />
                    ) : (
                      <CloseCircleOutlined style={{ fontSize: 16, color: '#ff4d4f' }} />
                    ),
                  children: (
                    <div>
                      <div style={{ fontWeight: 600 }}>
                        {r.case_title}
                        <Tag
                          color={r.status === 'passed' ? 'green' : 'red'}
                          style={{ marginLeft: 8 }}
                        >
                          {r.status}
                        </Tag>
                        {/* 重试标记：有多次尝试时展示 */}
                        {r.retry_attempts && r.retry_attempts.length > 1 && (
                          <Tag color="purple" style={{ marginLeft: 4 }}>
                            {r.status === 'passed'
                              ? `第 ${r.final_attempt} 次成功`
                              : `重试 ${r.retry_attempts.length - 1} 次仍失败`}
                          </Tag>
                        )}
                      </div>
                      <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                        步骤 {r.passed_steps}/{r.total_steps} · 耗时{' '}
                        {(r.duration || 0).toFixed(2)}s
                        {r.executed_at && (
                          <> · 开始 {dayjs(r.executed_at).format('HH:mm:ss')}</>
                        )}
                      </div>
                      {r.error && (
                        <div style={{ color: '#ff4d4f', fontSize: 12 }}>{r.error}</div>
                      )}
                    </div>
                  ),
                }))}
              />
            </Card>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 60 }}>加载中...</div>
        )}
      </Modal>
    </div>
  );
}
