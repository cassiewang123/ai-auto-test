import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  FileDoneOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
  SendOutlined,
  WarningOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  knowledgeBaseApi,
  projectApi,
  requirementApi,
  testDesignApi,
} from '../services/api';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type TestPoint = {
  id: string;
  module: string;
  point: string;
  category: string;
  priority: string;
  selected: boolean;
  trace_source?: string | null;
};

type TestDataRow = { field: string; value: string; note?: string };

type GeneratedCase = {
  id: string;
  title: string;
  module: string;
  category: string;
  priority: string;
  preconditions?: string | null;
  steps: string[];
  expected?: string | null;
  trace_source?: string | null;
  selected: boolean;
  imported_case_id?: string | null;
  /** 本用例实际使用的字段与取值 */
  test_data?: TestDataRow[];
  /** 接口自动化形态的请求定义与断言 */
  request_method?: string | null;
  request_url?: string | null;
  request_headers?: Record<string, unknown>;
  request_body?: unknown;
  assertions?: Array<Record<string, unknown>>;
  /** 有 method + url 才能被执行引擎直接跑 */
  executable?: boolean;
};

type Session = {
  id: string;
  title?: string | null;
  requirement_id?: string | null;
  requirement_title?: string | null;
  knowledge_base_id?: string | null;
  knowledge_base_name?: string | null;
  mode: string;
  status: string;
  engine: string;
  /** engine=llm 时的具体模型名 */
  engine_model?: string | null;
  /** engine=rule 时的回退原因，用于向用户解释为何没走大模型 */
  engine_fallback_reason?: string | null;
  /** manual 人工执行 / api 接口自动化 */
  output_mode?: string;
  prompt?: string | null;
  messages: Array<{ role: string; content: string; kind?: string }>;
  knowledge_refs: Array<{ chunk_id: string; document_name: string; score: number }>;
  review_dimensions: Record<string, number>;
  case_ids: string[];
  test_points: TestPoint[];
  cases: GeneratedCase[];
};

const CATEGORY_COLOR: Record<string, string> = {
  功能: 'blue',
  异常: 'volcano',
  边界: 'gold',
  权限: 'purple',
  安全: 'red',
};

/** 接口形态用例的请求方法配色 */
const METHOD_COLOR: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'purple',
  DELETE: 'red',
};

const PRIORITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'orange',
  P2: 'blue',
  P3: 'default',
};

const REVIEW_DIMENSIONS = [
  '覆盖完整性',
  '正确性',
  '冗余去重',
  '边界与异常',
  '步骤清晰度',
  '优先级合理性',
  '前置/数据完整性',
  '需求追溯',
];

const STATUS_LABEL: Record<string, string> = {
  clarifying: '待分析',
  points_ready: '测试点待确认',
  cases_ready: '用例待写入',
  imported: '已写入功能用例库',
};

const STATUS_COLOR: Record<string, string> = {
  clarifying: 'default',
  points_ready: 'processing',
  cases_ready: 'warning',
  imported: 'success',
};

export default function AiCaseGenerationPage() {
  const [requirements, setRequirements] = useState<any[]>([]);
  const [bases, setBases] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);

  const [requirementId, setRequirementId] = useState<string | undefined>();
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<string | undefined>();
  const [mode, setMode] = useState<'quick' | 'stepwise'>('quick');
  // 产出形态：manual 人工执行 / api 接口自动化（含可执行请求与断言）
  const [outputMode, setOutputMode] = useState<'manual' | 'api'>('manual');
  const [prompt, setPrompt] = useState('');
  const [reviewEnabled, setReviewEnabled] = useState(true);
  const [weights, setWeights] = useState<Record<string, number>>(
    Object.fromEntries(REVIEW_DIMENSIONS.map((name) => [name, 3]))
  );

  const [session, setSession] = useState<Session | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState('points');
  const [reviewResult, setReviewResult] = useState<any>(null);
  const [viewMode, setViewMode] = useState<'table' | 'card'>('table');
  const [selectedPointIds, setSelectedPointIds] = useState<string[]>([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [importOpen, setImportOpen] = useState(false);
  const [importProjectId, setImportProjectId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const res = await testDesignApi.listSessions({ page: 1, page_size: 50 });
      setSessions(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    requirementApi
      .list({ page: 1, page_size: 100 })
      .then((res) => setRequirements(res.data || []))
      .catch(() => {});
    knowledgeBaseApi
      .list({ page: 1, page_size: 100 })
      .then((res) => setBases(res.data || []))
      .catch(() => {});
    projectApi
      .listAll()
      .then((res) => setProjects(res.data || []))
      .catch(() => {});
    loadSessions();
  }, [loadSessions]);

  function applySession(next: Session | null) {
    setSession(next);
    setSelectedPointIds((next?.test_points || []).filter((p) => p.selected).map((p) => p.id));
    setSelectedCaseIds((next?.cases || []).filter((c) => c.selected).map((c) => c.id));
    if (next && next.test_points.length > 0) {
      setDetailTab('points');
    } else if (next && next.cases.length > 0) {
      setDetailTab('cases');
    }
  }

  async function startSession() {
    setBusy('create');
    try {
      const res = await testDesignApi.createSession({
        title: undefined,
        requirement_id: requirementId || null,
        knowledge_base_id: knowledgeBaseId || null,
        mode,
        output_mode: outputMode,
        prompt: prompt || null,
        review_dimensions: reviewEnabled ? weights : {},
      });
      message.success('已创建生成会话');
      applySession(res.data);
      await loadSessions();
      await generatePoints(res.data.id);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function generatePoints(sessionId: string) {
    setBusy('points');
    try {
      const res = await testDesignApi.generatePoints(sessionId);
      applySession(res.data);
      setDetailTab('points');
      message.success(`已生成 ${res.data.test_points.length} 个测试点，请确认后生成用例`);
      await loadSessions();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function savePointChanges(pointId: string, changes: Partial<TestPoint>) {
    if (!session) return;
    try {
      const res = await testDesignApi.updatePoints(session.id, [
        { id: pointId, ...changes },
      ]);
      setSession(res.data);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function togglePoints(selected: boolean) {
    if (!session) return;
    const targets = selected
      ? selectedPointIds
      : session.test_points
          .filter((point) => selectedPointIds.includes(point.id))
          .map((point) => point.id);
    if (targets.length === 0) {
      message.warning('请先勾选测试点');
      return;
    }
    try {
      const res = await testDesignApi.updatePoints(
        session.id,
        targets.map((id) => ({ id, selected }))
      );
      setSession(res.data);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function confirmPointsAndGenerateCases(onlySelected: boolean) {
    if (!session) return;
    setBusy('cases');
    try {
      // 先把勾选状态写回，确保后端按最新确认结果生成
      await testDesignApi.updatePoints(
        session.id,
        session.test_points.map((point) => ({
          id: point.id,
          selected: selectedPointIds.includes(point.id),
        }))
      );
      const res = await testDesignApi.generateCases(
        session.id,
        onlySelected ? selectedPointIds : undefined
      );
      applySession(res.data.session);
      setDetailTab('cases');
      message.success(`已生成 ${res.data.case_count} 条用例草稿`);
      await loadSessions();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleReview() {
    if (!session) return;
    setBusy('review');
    try {
      const res = await testDesignApi.review(
        session.id,
        reviewEnabled ? weights : {}
      );
      setReviewResult(res.data);
      setDetailTab('review');
      message.success(`多维度评审完成，综合得分 ${res.data.overall_score}`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleSendMessage() {
    const text = chatInput.trim();
    if (!text || !session) return;
    setBusy('chat');
    try {
      const res = await testDesignApi.sendMessage(session.id, text);
      setSession(res.data);
      setChatInput('');
      message.success('已记录补充信息，可重新拆解测试点');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleImport() {
    if (!session) return;
    setBusy('import');
    try {
      const res = await testDesignApi.importCases(
        session.id,
        selectedCaseIds.length > 0 ? selectedCaseIds : undefined,
        importProjectId
      );
      message.success(`已写入功能测试用例库 ${res.data.created_count} 条用例`);
      setImportOpen(false);
      const detail = await testDesignApi.getSession(session.id);
      applySession(detail.data);
      await loadSessions();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function removeSession(id: string) {
    try {
      await testDesignApi.removeSession(id);
      message.success('会话已删除');
      if (session?.id === id) applySession(null);
      await loadSessions();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const pendingCount = useMemo(
    () => (session?.test_points || []).filter((p) => p.selected).length,
    [session]
  );

  const pointColumns = [
    {
      title: '模块',
      dataIndex: 'module',
      width: 150,
      render: (value: string, record: TestPoint) => (
        <Input
          size="small"
          defaultValue={value}
          onBlur={(e) => {
            const next = e.target.value.trim();
            if (next && next !== value) savePointChanges(record.id, { module: next });
          }}
        />
      ),
    },
    {
      title: '测试点',
      dataIndex: 'point',
      render: (value: string, record: TestPoint) => (
        <Input
          size="small"
          defaultValue={value}
          onBlur={(e) => {
            const next = e.target.value.trim();
            if (next && next !== value) savePointChanges(record.id, { point: next });
          }}
        />
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (value: string) => (
        <Tag color={CATEGORY_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (value: string) => (
        <Tag color={PRIORITY_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '需求追溯',
      dataIndex: 'trace_source',
      width: 200,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
  ];

  const caseColumns = [
    { title: '用例标题', dataIndex: 'title', ellipsis: true },
    {
      title: '模块',
      dataIndex: 'module',
      width: 130,
      ellipsis: true,
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 90,
      render: (value: string) => (
        <Tag color={CATEGORY_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (value: string) => (
        <Tag color={PRIORITY_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '步骤',
      dataIndex: 'steps',
      width: 80,
      render: (value: string[]) => value?.length || 0,
    },
    {
      title: '状态',
      dataIndex: 'imported_case_id',
      width: 110,
      render: (value: string | null) =>
        value ? <Tag color="success">已写入</Tag> : <Tag>草稿</Tag>,
    },
  ];

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card
          size="small"
          title="生成会话"
          extra={
            <Button size="small" icon={<ReloadOutlined />} onClick={loadSessions}>
              刷新
            </Button>
          }
          loading={sessionsLoading}
        >
          {sessions.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有生成会话" />
          ) : (
            <List
              dataSource={sessions}
              renderItem={(item) => (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    background:
                      item.id === session?.id ? 'rgba(22,119,255,0.08)' : undefined,
                    borderRadius: 6,
                    paddingInline: 8,
                  }}
                  onClick={async () => {
                    try {
                      const res = await testDesignApi.getSession(item.id);
                      applySession(res.data);
                    } catch (e: any) {
                      message.error(e.message);
                    }
                  }}
                  actions={[
                    <Popconfirm
                      key="del"
                      title="确认删除该会话？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        removeSession(item.id);
                      }}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={item.title || '未命名会话'}
                    description={
                      <Space direction="vertical" size={0}>
                        <Tag color={STATUS_COLOR[item.status] || 'default'}>
                          {STATUS_LABEL[item.status] || item.status}
                        </Tag>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {item.mode === 'stepwise' ? '分步生成' : '快速生成'} ·{' '}
                          {item.test_points?.length || 0} 测试点 /{' '}
                          {item.cases?.length || 0} 用例
                        </Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      </Col>

      <Col span={18}>
        <Card
          size="small"
          title={
            <Space>
              <RobotOutlined />
              <span>AI 测试用例生成</span>
            </Space>
          }
        >
          <Row gutter={16}>
            <Col span={14}>
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                <div>
                  <Text type="secondary">需求文档（可选）</Text>
                  <Select
                    allowClear
                    style={{ width: '100%' }}
                    placeholder="选择已创建的需求，作为本次用例生成依据"
                    value={requirementId}
                    onChange={setRequirementId}
                    options={requirements.map((item) => ({
                      label: item.title,
                      value: item.id,
                    }))}
                    showSearch
                    optionFilterProp="label"
                  />
                </div>
                <div>
                  <Text type="secondary">知识库 RAG（可选）</Text>
                  <Select
                    allowClear
                    style={{ width: '100%' }}
                    placeholder="选择知识库，补充技术与业务上下文"
                    value={knowledgeBaseId}
                    onChange={setKnowledgeBaseId}
                    options={bases.map((item) => ({
                      label: `${item.name}（${item.document_count || 0} 个文件）`,
                      value: item.id,
                    }))}
                    showSearch
                    optionFilterProp="label"
                  />
                </div>
                <TextArea
                  rows={3}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="描述要测的范围，例如：覆盖登录失败与锁定策略"
                />
                <Space wrap>
                  <Segmented
                    value={mode}
                    onChange={(value) => setMode(value as 'quick' | 'stepwise')}
                    options={[
                      { label: '快速生成', value: 'quick' },
                      { label: '分步生成（需求分析 → 测试点 → 用例）', value: 'stepwise' },
                    ]}
                  />
                  <Tooltip title="人工执行：前置条件+步骤+预期+测试数据；接口自动化：额外生成可执行的请求与断言">
                    <Segmented
                      value={outputMode}
                      onChange={(value) => setOutputMode(value as 'manual' | 'api')}
                      options={[
                        { label: '人工执行', value: 'manual' },
                        { label: '接口自动化', value: 'api' },
                      ]}
                    />
                  </Tooltip>
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    loading={busy === 'create' || busy === 'points'}
                    onClick={startSession}
                  >
                    创建并生成测试点
                  </Button>
                </Space>
              </Space>
            </Col>
            <Col span={10}>
              <Card
                size="small"
                title={
                  <Space>
                    <span>用例评审（AI 多维检查）</span>
                    <Switch
                      size="small"
                      checked={reviewEnabled}
                      onChange={setReviewEnabled}
                    />
                  </Space>
                }
                style={{ maxHeight: 300, overflow: 'auto' }}
              >
                <Text type="secondary" style={{ fontSize: 12 }}>
                  勾选维度并设置权重（1-5，越高越优先）
                </Text>
                <div style={{ marginTop: 8 }}>
                  {REVIEW_DIMENSIONS.map((name) => (
                    <Row key={name} align="middle" style={{ marginBottom: 4 }}>
                      <Col span={14}>
                        <Text style={{ fontSize: 12 }}>{name}</Text>
                      </Col>
                      <Col span={10}>
                        <Select
                          size="small"
                          style={{ width: '100%' }}
                          disabled={!reviewEnabled}
                          value={weights[name]}
                          onChange={(value) =>
                            setWeights((prev) => ({ ...prev, [name]: value }))
                          }
                          options={[1, 2, 3, 4, 5].map((value) => ({
                            label: String(value),
                            value,
                          }))}
                        />
                      </Col>
                    </Row>
                  ))}
                </div>
              </Card>
            </Col>
          </Row>
        </Card>

        {!session ? (
          <Card style={{ marginTop: 16 }}>
            <Empty description="创建会话后，先确认测试点，再生成用例" />
          </Card>
        ) : (
          <Card
            size="small"
            style={{ marginTop: 16 }}
            title={
              <Space>
                <span>{session.title || '未命名会话'}</span>
                <Tag color={STATUS_COLOR[session.status]}>
                  {STATUS_LABEL[session.status] || session.status}
                </Tag>
                {session.engine === 'llm' ? (
                  <Tooltip
                    title={`由大模型 ${session.engine_model || ''} 生成，步骤与测试数据为模型产出`}
                  >
                    <Tag color="green" icon={<RobotOutlined />}>
                      {session.engine_model
                        ? `大模型 · ${session.engine_model}`
                        : '大模型生成'}
                    </Tag>
                  </Tooltip>
                ) : (
                  <Tooltip
                    title={
                      session.engine_fallback_reason
                        ? `未使用大模型：${session.engine_fallback_reason}`
                        : '未使用大模型，内容由内置模板生成，步骤较笼统'
                    }
                  >
                    <Tag color="orange" icon={<WarningOutlined />}>
                      规则引擎（未用大模型）
                    </Tag>
                  </Tooltip>
                )}
              </Space>
            }
            extra={
              <Space wrap>
                <Button
                  icon={<ExperimentOutlined />}
                  loading={busy === 'points'}
                  onClick={() => generatePoints(session.id)}
                >
                  重新拆解测试点
                </Button>
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  loading={busy === 'cases'}
                  disabled={pendingCount === 0}
                  onClick={() => confirmPointsAndGenerateCases(true)}
                >
                  确认测试点并生成用例（{pendingCount}）
                </Button>
                <Button loading={busy === 'review'} onClick={handleReview}>
                  多维评审
                </Button>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  disabled={session.cases.length === 0}
                  onClick={() => setImportOpen(true)}
                >
                  写入功能用例库
                </Button>
              </Space>
            }
          >
            {/* 明确告知本次结果由哪个引擎产出：规则引擎的步骤与测试数据
                只有模板级别，用户需要知道并据此决定是否重新生成 */}
            {session.engine === 'llm' ? (
              <Alert
                type="success"
                showIcon
                style={{ marginBottom: 12 }}
                message={`本会话内容由大模型生成${
                  session.engine_model ? `（${session.engine_model}）` : ''
                }，步骤与测试数据来自模型对需求的理解`}
              />
            ) : (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="本会话内容由规则引擎生成，未调用大模型"
                description={
                  <span>
                    规则引擎只做关键词推断，操作步骤和测试数据会比较笼统。
                    {session.engine_fallback_reason
                      ? `未使用大模型的原因：${session.engine_fallback_reason}。`
                      : ''}
                    修复配置后点「重新拆解测试点」即可用大模型重新生成。
                  </span>
                }
              />
            )}
            <Tabs
              activeKey={detailTab}
              onChange={setDetailTab}
              items={[
                {
                  key: 'points',
                  label: `测试点 (${session.test_points.length})`,
                  children: (
                    <>
                      <Space style={{ marginBottom: 8 }}>
                        <Text type="secondary">
                          先确认测试点再生成用例，可降低人工审核成本
                        </Text>
                        <Button size="small" onClick={() => togglePoints(true)}>
                          全选
                        </Button>
                        <Button size="small" onClick={() => togglePoints(false)}>
                          取消全选
                        </Button>
                      </Space>
                      <Table
                        rowKey="id"
                        size="small"
                        dataSource={session.test_points}
                        columns={pointColumns}
                        pagination={{ pageSize: 10, showSizeChanger: false }}
                        rowSelection={{
                          selectedRowKeys: selectedPointIds,
                          onChange: (keys) => setSelectedPointIds(keys as string[]),
                        }}
                        scroll={{ x: 900 }}
                      />
                    </>
                  ),
                },
                {
                  key: 'cases',
                  label: `用例草稿 (${session.cases.length})`,
                  children: (
                    <>
                      <Space style={{ marginBottom: 8 }}>
                        <Segmented
                          size="small"
                          value={viewMode}
                          onChange={(value) => setViewMode(value as 'table' | 'card')}
                          options={[
                            { label: '表格', value: 'table' },
                            { label: '卡片', value: 'card' },
                          ]}
                        />
                        <Button size="small" onClick={() => setSelectedCaseIds(session.cases.map((c) => c.id))}>
                          全选
                        </Button>
                        <Button size="small" onClick={() => setSelectedCaseIds([])}>
                          取消全选
                        </Button>
                      </Space>
                      {viewMode === 'table' ? (
                        <Table
                          rowKey="id"
                          size="small"
                          dataSource={session.cases}
                          columns={caseColumns}
                          pagination={{ pageSize: 10, showSizeChanger: false }}
                          rowSelection={{
                            selectedRowKeys: selectedCaseIds,
                            onChange: (keys) => setSelectedCaseIds(keys as string[]),
                          }}
                          expandable={{
                            expandedRowRender: (record: GeneratedCase) => (
                              <div style={{ paddingLeft: 8 }}>
                                <Paragraph>
                                  <Text strong>前置条件：</Text>
                                  {record.preconditions || '-'}
                                </Paragraph>
                                <Paragraph>
                                  <Text strong>操作步骤：</Text>
                                </Paragraph>
                                <ol style={{ marginTop: 0 }}>
                                  {(record.steps || []).map((step, index) => (
                                    <li key={index}>{step}</li>
                                  ))}
                                </ol>
                                <Paragraph>
                                  <Text strong>预期结果：</Text>
                                  {record.expected || '-'}
                                </Paragraph>

                                {/* 测试数据：直接照着填的字段与取值 */}
                                {record.test_data && record.test_data.length > 0 && (
                                  <>
                                    <Paragraph style={{ marginBottom: 4 }}>
                                      <Text strong>测试数据：</Text>
                                    </Paragraph>
                                    <Table<TestDataRow>
                                      size="small"
                                      rowKey={(row) => `${row.field}-${row.value}`}
                                      pagination={false}
                                      dataSource={record.test_data}
                                      columns={[
                                        { title: '字段', dataIndex: 'field', width: 160 },
                                        {
                                          title: '取值',
                                          dataIndex: 'value',
                                          render: (v: string) => <Text code>{v || '(空)'}</Text>,
                                        },
                                        { title: '构造意图', dataIndex: 'note' },
                                      ]}
                                    />
                                  </>
                                )}

                                {/* 接口形态：请求与断言，可直接导入接口库执行 */}
                                {record.executable && (
                                  <>
                                    <Paragraph style={{ marginTop: 12, marginBottom: 4 }}>
                                      <Text strong>接口请求：</Text>
                                      <Tag color={METHOD_COLOR[record.request_method || ''] || 'default'}>
                                        {record.request_method}
                                      </Tag>
                                      <Text code>{record.request_url}</Text>
                                    </Paragraph>
                                    {record.request_headers &&
                                      Object.keys(record.request_headers).length > 0 && (
                                        <Paragraph style={{ marginBottom: 4 }}>
                                          <Text strong>请求头：</Text>
                                          <Text code>{JSON.stringify(record.request_headers)}</Text>
                                        </Paragraph>
                                      )}
                                    <Paragraph style={{ marginBottom: 4 }}>
                                      <Text strong>请求体：</Text>
                                      <Text code>{JSON.stringify(record.request_body ?? null)}</Text>
                                    </Paragraph>
                                    <Paragraph style={{ marginBottom: 0 }}>
                                      <Text strong>断言：</Text>
                                      <Text code>{JSON.stringify(record.assertions || [])}</Text>
                                    </Paragraph>
                                  </>
                                )}
                              </div>
                            ),
                          }}
                        />
                      ) : (
                        <Row gutter={[12, 12]}>
                          {session.cases.map((item) => (
                            <Col key={item.id} xs={24} md={12} xl={8}>
                              <Card
                                size="small"
                                title={
                                  <Tooltip title={item.title}>
                                    <Text ellipsis style={{ maxWidth: 220 }}>
                                      {item.title}
                                    </Text>
                                  </Tooltip>
                                }
                                extra={<Tag color={PRIORITY_COLOR[item.priority]}>{item.priority}</Tag>}
                              >
                                <Space size={4} wrap style={{ marginBottom: 6 }}>
                                  <Tag color={CATEGORY_COLOR[item.category]}>
                                    {item.category}
                                  </Tag>
                                  <Tag>{item.module}</Tag>
                                  {item.imported_case_id && (
                                    <Tag color="success">已写入</Tag>
                                  )}
                                </Space>
                                <Paragraph
                                  type="secondary"
                                  style={{ fontSize: 12, marginBottom: 4 }}
                                >
                                  {item.preconditions || '无前置条件'}
                                </Paragraph>
                                <ol style={{ paddingLeft: 18, fontSize: 12, marginBottom: 4 }}>
                                  {(item.steps || []).slice(0, 4).map((step, index) => (
                                    <li key={index}>{step}</li>
                                  ))}
                                </ol>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  预期：{item.expected}
                                </Text>
                              </Card>
                            </Col>
                          ))}
                        </Row>
                      )}
                    </>
                  ),
                },
                {
                  key: 'review',
                  label: '多维度评审',
                  children: !reviewResult ? (
                    <Empty description="点击「多维评审」生成评审报告" />
                  ) : (
                    <Row gutter={16}>
                      <Col span={8}>
                        <Statistic
                          title="综合得分"
                          value={reviewResult.overall_score}
                          suffix="/100"
                        />
                        <div style={{ marginTop: 12 }}>
                          {Object.entries(reviewResult.dimension_scores || {}).map(
                            ([name, score]) => (
                              <div key={name} style={{ marginBottom: 6 }}>
                                <Text style={{ fontSize: 12 }}>{name}</Text>
                                <Progress
                                  percent={Number(score)}
                                  size="small"
                                  status={Number(score) >= 60 ? 'normal' : 'exception'}
                                />
                              </div>
                            )
                          )}
                        </div>
                      </Col>
                      <Col span={16}>
                        <Card size="small" title="发现的问题">
                          {(reviewResult.issues || []).length === 0 ? (
                            <Empty description="未发现问题" />
                          ) : (
                            <List
                              size="small"
                              dataSource={reviewResult.issues}
                              renderItem={(issue: any) => (
                                <List.Item>
                                  <Space>
                                    <Tag color={issue.level === 'error' ? 'red' : 'orange'}>
                                      {issue.dimension}
                                    </Tag>
                                    <Text>{issue.message}</Text>
                                  </Space>
                                </List.Item>
                              )}
                            />
                          )}
                        </Card>
                      </Col>
                    </Row>
                  ),
                },
                {
                  key: 'chat',
                  label: `对话 (${session.messages.length})`,
                  children: (
                    <>
                      <div
                        style={{
                          maxHeight: 320,
                          overflow: 'auto',
                          marginBottom: 12,
                        }}
                      >
                        {session.messages.length === 0 ? (
                          <Alert
                            type="info"
                            showIcon
                            message="分步生成时，AI 会在此提出缺失信息的问题，可直接回复补充"
                          />
                        ) : (
                          session.messages.map((item, index) => (
                            <div key={index} style={{ marginBottom: 10 }}>
                              <Tag color={item.role === 'user' ? 'blue' : 'green'}>
                                {item.role === 'user' ? '我' : '助手'}
                              </Tag>
                              <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>
                                {item.content}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                      <Space.Compact style={{ width: '100%' }}>
                        <Input
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          onPressEnter={handleSendMessage}
                          placeholder="补充业务规则、异常处理或修改要求"
                        />
                        <Button
                          type="primary"
                          icon={<SendOutlined />}
                          loading={busy === 'chat'}
                          onClick={handleSendMessage}
                        >
                          发送
                        </Button>
                      </Space.Compact>
                      {session.knowledge_refs.length > 0 && (
                        <Collapse
                          style={{ marginTop: 12 }}
                          items={[
                            {
                              key: 'refs',
                              label: `引用的知识库分块（${session.knowledge_refs.length}）`,
                              children: (
                                <List
                                  size="small"
                                  dataSource={session.knowledge_refs}
                                  renderItem={(ref: any) => (
                                    <List.Item>
                                      {ref.document_name} · 相关度{' '}
                                      {Math.round((ref.score || 0) * 100)}%
                                    </List.Item>
                                  )}
                                />
                              ),
                            },
                          ]}
                        />
                      )}
                    </>
                  ),
                },
              ]}
            />
          </Card>
        )}
      </Col>

      <Modal
        title="写入功能测试用例库"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={handleImport}
        confirmLoading={busy === 'import'}
        okText="确认写入"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            icon={<FileDoneOutlined />}
            message={`将写入 ${selectedCaseIds.length || session?.cases.length || 0} 条用例到功能测试用例库`}
            description="这些是功能测试用例（前置条件 / 操作步骤 / 预期结果），写入后不会出现在 API 自动化「用例管理」中；可在「功能测试用例」页查看、编辑与登记执行结果"
          />
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="目标项目">
              <Select
                allowClear
                style={{ width: '100%' }}
                placeholder="不指定则跟随会话所属项目"
                value={importProjectId || undefined}
                onChange={(value) => setImportProjectId(value || null)}
                options={projects.map((item) => ({
                  label: item.name,
                  value: item.id,
                }))}
                showSearch
                optionFilterProp="label"
              />
            </Descriptions.Item>
            <Descriptions.Item label="关联需求">
              {session?.requirement_title || '-'}
            </Descriptions.Item>
          </Descriptions>
        </Space>
      </Modal>
    </Row>
  );
}
