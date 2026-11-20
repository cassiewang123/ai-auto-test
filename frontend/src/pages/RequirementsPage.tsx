import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  AuditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileAddOutlined,
  FileTextOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SendOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { knowledgeBaseApi, requirementApi } from '../services/api';

const { TextArea } = Input;
const { Text, Title } = Typography;

type Requirement = {
  id: string;
  title: string;
  description?: string | null;
  source?: string;
  priority: string;
  status: string;
  acceptance_criteria?: string | null;
  case_ids?: string[];
  project_id?: string | null;
  coverage?: number;
  created_at?: string;
};

type RequirementDocument = {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  char_count: number;
  warnings?: string[];
  created_at?: string;
};

type FunctionItem = { module?: string; points?: string[] | string };
type UiDescription = { page?: string; description?: string };
type Clarification = { question?: string; reason?: string };

type Analysis = {
  id: string;
  engine: string;
  knowledge_base_id?: string | null;
  function_items: FunctionItem[];
  ui_descriptions: UiDescription[];
  clarifications: Clarification[];
  markdown?: string | null;
  messages: Array<{ role: string; content: string }>;
  created_at?: string;
};

const STATUS_OPTIONS = [
  { label: '草稿', value: 'draft' },
  { label: '进行中', value: 'active' },
  { label: '已覆盖', value: 'covered' },
  { label: '已归档', value: 'archived' },
];

const STATUS_COLOR: Record<string, string> = {
  draft: 'default',
  active: 'processing',
  covered: 'success',
  archived: 'default',
};

const PRIORITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'orange',
  P2: 'blue',
  P3: 'default',
};

const ACCEPT_PATTERN =
  '.pdf,.docx,.md,.markdown,.txt,.log,.json,.csv,.png,.jpg,.jpeg,.webp,.bmp';

function formatBytes(size: number): string {
  if (!size) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export default function RequirementsPage() {
  const [data, setData] = useState<Requirement[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [stats, setStats] = useState<Record<string, number>>({});

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Requirement | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  // 分析抽屉
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [activeRequirement, setActiveRequirement] = useState<Requirement | null>(null);
  const [documents, setDocuments] = useState<RequirementDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisTab, setAnalysisTab] = useState('functions');
  const [knowledgeBases, setKnowledgeBases] = useState<any[]>([]);
  const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState<string | undefined>();
  const [chatInput, setChatInput] = useState('');
  const [sendingChat, setSendingChat] = useState(false);
  const [history, setHistory] = useState<Analysis[]>([]);

  const loadData = useCallback(
    async (p = page, ps = pageSize, st = status) => {
      setLoading(true);
      try {
        const res = await requirementApi.list({
          page: p,
          page_size: ps,
          status: st,
          keyword: keyword || undefined,
        });
        setData(res.data || []);
        setTotal(res.total || 0);
      } catch (e: any) {
        message.error(e.message);
      } finally {
        setLoading(false);
      }
    },
    [keyword, page, pageSize, status]
  );

  const loadStats = useCallback(async () => {
    try {
      const res = await requirementApi.stats();
      setStats(res.data || {});
    } catch {
      // 统计失败不阻断主列表
    }
  }, []);

  useEffect(() => {
    loadData(1, pageSize, status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    knowledgeBaseApi
      .list({ page: 1, page_size: 100 })
      .then((res) => setKnowledgeBases(res.data || []))
      .catch(() => {});
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ priority: 'P1', status: 'draft' });
    setModalOpen(true);
  }

  function openEdit(record: Requirement) {
    setEditing(record);
    form.setFieldsValue({
      title: record.title,
      description: record.description || '',
      acceptance_criteria: record.acceptance_criteria || '',
      priority: record.priority,
      status: record.status,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (editing) {
        await requirementApi.update(editing.id, values);
        message.success('需求已更新');
      } else {
        await requirementApi.create(values);
        message.success('需求已创建');
      }
      setModalOpen(false);
      await loadData();
      await loadStats();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(record: Requirement) {
    try {
      await requirementApi.remove(record.id);
      message.success('需求已删除');
      await loadData();
      await loadStats();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // ---------------- 需求分析 ----------------
  async function openAnalysis(record: Requirement) {
    setActiveRequirement(record);
    setAnalysisOpen(true);
    setAnalysis(null);
    setAnalysisTab('functions');
    setSelectedKnowledgeBase(undefined);
    setChatInput('');
    await Promise.all([loadDocuments(record.id), loadAnalyses(record.id)]);
  }

  async function loadDocuments(requirementId: string) {
    setDocumentsLoading(true);
    try {
      const res = await requirementApi.listDocuments(requirementId);
      setDocuments(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function loadAnalyses(requirementId: string) {
    try {
      const res = await requirementApi.listAnalyses(requirementId);
      const items = res.data || [];
      setHistory(items);
      if (items.length > 0) {
        setAnalysis(items[0]);
      }
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleUpload(file: File) {
    if (!activeRequirement) return false;
    try {
      const res = await requirementApi.uploadDocument(activeRequirement.id, file);
      const uploaded = res.data;
      if (uploaded?.warnings?.length) {
        message.warning(uploaded.warnings[0]);
      } else {
        message.success(`${file.name} 已导入`);
      }
      await loadDocuments(activeRequirement.id);
    } catch (e: any) {
      message.error(e.message);
    }
    return false;
  }

  async function handleDeleteDocument(documentId: string) {
    if (!activeRequirement) return;
    try {
      await requirementApi.deleteDocument(activeRequirement.id, documentId);
      message.success('文档已删除');
      await loadDocuments(activeRequirement.id);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleAnalyze() {
    if (!activeRequirement) return;
    setAnalyzing(true);
    try {
      const res = await requirementApi.analyze(activeRequirement.id, {
        knowledge_base_id: selectedKnowledgeBase || null,
        use_documents: true,
      });
      setAnalysis(res.data);
      setAnalysisTab('functions');
      message.success(
        res.data?.engine === 'llm' ? 'AI 分析完成' : '规则引擎分析完成（未启用外部 LLM）'
      );
      await loadAnalyses(activeRequirement.id);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleSendChat() {
    const text = chatInput.trim();
    if (!text || !analysis) {
      if (!analysis) message.warning('请先执行一次分析');
      return;
    }
    setSendingChat(true);
    try {
      const res = await requirementApi.continueAnalysis(analysis.id, text);
      setAnalysis(res.data);
      setChatInput('');
      await loadAnalyses(activeRequirement!.id);
      message.success('已按补充要求重新梳理');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSendingChat(false);
    }
  }

  function handleExport() {
    if (!analysis) return;
    // 通过后端导出接口下载 Markdown 文件
    const url = requirementApi.exportAnalysisUrl(analysis.id);
    const token = localStorage.getItem('access_token');
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((res) => {
        if (!res.ok) throw new Error('导出失败');
        return res.blob();
      })
      .then((blob) => {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `需求分析-${activeRequirement?.title || analysis.id}.md`;
        link.click();
        URL.revokeObjectURL(link.href);
      })
      .catch((e) => message.error(e.message));
  }

  const functionCount = useMemo(
    () =>
      (analysis?.function_items || []).reduce((sum, item) => {
        const points = Array.isArray(item.points)
          ? item.points.length
          : item.points
            ? 1
            : 0;
        return sum + points;
      }, 0),
    [analysis]
  );

  const columns = [
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (value: string) => <Tag>{value === 'manual' ? '手工' : value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={STATUS_COLOR[value] || 'default'}>
          {STATUS_OPTIONS.find((item) => item.value === value)?.label || value}
        </Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (value: string) => <Tag color={PRIORITY_COLOR[value] || 'default'}>{value}</Tag>,
    },
    {
      title: '关联用例',
      dataIndex: 'coverage',
      width: 100,
      render: (value: number) => value || 0,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => (value ? new Date(value).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 260,
      render: (_: unknown, record: Requirement) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openAnalysis(record)}>
            需求分析
          </Button>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该需求？" onConfirm={() => handleDelete(record)}>
            <Button type="link" size="small" danger>
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
            <FileTextOutlined />
            <span>需求管理</span>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索需求标题"
             allowClear
              style={{ width: 220 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={() => loadData(1, pageSize, status)}
            />
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 120 }}
              value={status}
              onChange={(value) => {
                setStatus(value);
                setPage(1);
              }}
              options={STATUS_OPTIONS}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建需求
            </Button>
          </Space>
        }
      >
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[
            { label: '需求总数', value: stats.total || 0 },
            { label: '草稿', value: stats.draft || 0 },
            { label: '进行中', value: stats.active || 0 },
            { label: '已覆盖', value: stats.covered || 0 },
            { label: '关联用例', value: stats.total_cases || 0 },
          ].map((item) => (
            <Col key={item.label} xs={12} sm={8} md={4}>
              <Card size="small">
                <Text type="secondary">{item.label}</Text>
                <Title level={4} style={{ margin: 0 }}>
                  {item.value}
                </Title>
              </Card>
            </Col>
          ))}
        </Row>

        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          columns={columns}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
              loadData(p, ps, status);
            },
          }}
        />
      </Card>

      <Modal
        title={editing ? '编辑需求' : '新建需求'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        width={720}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入需求标题' }]}
          >
            <Input placeholder="例如：登录、项目、需求管理需求" />
          </Form.Item>
          <Form.Item
            name="description"
            label="需求正文"
            extra="需求文档可在「需求分析」中上传 PDF / Word / Markdown / 纯文本 / 图片"
          >
            <TextArea rows={8} placeholder="描述本次需求的功能范围" />
          </Form.Item>
          <Form.Item name="acceptance_criteria" label="验收标准">
            <TextArea rows={3} placeholder="可选：验收通过的判定条件" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="priority" label="优先级">
                <Select
                  options={['P0', 'P1', 'P2', 'P3'].map((value) => ({
                    label: value,
                    value,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态">
                <Select options={STATUS_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Drawer
        title={
          <Space>
            <AuditOutlined />
            <span>需求分析：{activeRequirement?.title}</span>
          </Space>
        }
        open={analysisOpen}
        onClose={() => setAnalysisOpen(false)}
        width="min(1280px, 96vw)"
        destroyOnClose
      >
        <Row gutter={16}>
          <Col span={17}>
            <Card
              size="small"
              title="需求文档"
              extra={
                <Upload
                  accept={ACCEPT_PATTERN}
                  showUploadList={false}
                  beforeUpload={handleUpload}
                >
                  <Button icon={<UploadOutlined />} size="small">
                    上传附件
                  </Button>
                </Upload>
              }
              style={{ marginBottom: 12 }}
            >
              <Text type="secondary">
                支持图片、PDF、DOCX、txt/md/log/json、csv，单文件 &lt;20MB；图片不做 OCR，需补充正文
              </Text>
              <Spin spinning={documentsLoading}>
                {documents.length === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="尚未上传需求文档"
                  />
                ) : (
                  <List
                    size="small"
                    dataSource={documents}
                    renderItem={(item) => (
                      <List.Item
                        actions={[
                          <Button
                            key="delete"
                            type="link"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => handleDeleteDocument(item.id)}
                          >
                            删除
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <Space>
                              <FileAddOutlined />
                              {item.filename}
                              <Tag>{item.file_type}</Tag>
                            </Space>
                          }
                          description={
                            <Space split="|">
                              <span>{formatBytes(item.file_size)}</span>
                              <span>{item.char_count} 字符</span>
                              {item.warnings && item.warnings.length > 0 && (
                                <Tooltip title={item.warnings.join('\n')}>
                                  <Tag color="orange">解析告警</Tag>
                                </Tooltip>
                              )}
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Spin>
            </Card>

            <Card
              size="small"
              title={
                <Space>
                  <RobotOutlined />
                  <span>AI 结构化分析</span>
                  {analysis && (
                    <Tag color={analysis.engine === 'llm' ? 'green' : 'blue'}>
                      {analysis.engine === 'llm' ? 'LLM' : '规则引擎'}
                    </Tag>
                  )}
                </Space>
              }
              extra={
                <Space>
                  <Select
                    allowClear
                    placeholder="引用知识库（可选）"
                    style={{ width: 220 }}
                    value={selectedKnowledgeBase}
                    onChange={setSelectedKnowledgeBase}
                    options={knowledgeBases.map((item) => ({
                      label: item.name,
                      value: item.id,
                    }))}
                  />
                  <Button
                    type="primary"
                    loading={analyzing}
                    onClick={handleAnalyze}
                    icon={<RobotOutlined />}
                  >
                    重新分析
                  </Button>
                  <Button
                    icon={<DownloadOutlined />}
                    disabled={!analysis}
                    onClick={handleExport}
                  >
                    导出 Markdown
                  </Button>
                </Space>
              }
            >
              {!analysis ? (
                <Empty description="点击「重新分析」生成功能清单、界面描述与待澄清项" />
              ) : (
                <Tabs
                  activeKey={analysisTab}
                  onChange={setAnalysisTab}
                  items={[
                    {
                      key: 'functions',
                      label: `功能清单 (${functionCount})`,
                      children: (
                        <div style={{ maxHeight: 460, overflow: 'auto' }}>
                          {(analysis.function_items || []).length === 0 ? (
                            <Empty description="未识别出功能模块" />
                          ) : (
                            analysis.function_items.map((item, index) => (
                              <Card
                                key={`${item.module}-${index}`}
                                size="small"
                                style={{ marginBottom: 8 }}
                                title={item.module || '通用功能'}
                              >
                                <ul style={{ margin: 0, paddingLeft: 20 }}>
                                  {(
                                    Array.isArray(item.points)
                                      ? item.points
                                      : [item.points]
                                  )
                                    .filter((point): point is string => Boolean(point))
                                    .map((point, i) => (
                                      <li key={i}>{point}</li>
                                    ))}
                                </ul>
                              </Card>
                            ))
                          )}
                        </div>
                      ),
                    },
                    {
                      key: 'ui',
                      label: `界面描述 (${(analysis.ui_descriptions || []).length})`,
                      children: (
                        <div style={{ maxHeight: 460, overflow: 'auto' }}>
                          {(analysis.ui_descriptions || []).length === 0 ? (
                            <Empty description="本次需求未涉及界面交互描述" />
                          ) : (
                            analysis.ui_descriptions.map((item, index) => (
                              <Card
                                key={index}
                                size="small"
                                style={{ marginBottom: 8 }}
                                title={item.page || '全局交互'}
                              >
                                <Text>{item.description}</Text>
                              </Card>
                            ))
                          )}
                        </div>
                      ),
                    },
                    {
                      key: 'clarifications',
                      label: `待澄清项 (${(analysis.clarifications || []).length})`,
                      children: (
                        <div style={{ maxHeight: 460, overflow: 'auto' }}>
                          {(analysis.clarifications || []).length === 0 ? (
                            <Empty description="未发现明显待澄清项" />
                          ) : (
                            <List
                              size="small"
                              dataSource={analysis.clarifications}
                              renderItem={(item, index) => (
                                <List.Item>
                                  <List.Item.Meta
                                    title={`${index + 1}. ${item.question || ''}`}
                                    description={
                                      item.reason ? `原因：${item.reason}` : undefined
                                    }
                                  />
                                </List.Item>
                              )}
                            />
                          )}
                        </div>
                      ),
                    },
                  ]}
                />
              )}
            </Card>
          </Col>

          <Col span={7}>
            <Card
              size="small"
              title={
                <Space>
                  <MessageOutlined />
                  <span>对话调整</span>
                </Space>
              }
              style={{ height: '100%' }}
            >
              <div
                style={{
                  maxHeight: 480,
                  minHeight: 260,
                  overflow: 'auto',
                  marginBottom: 12,
                  paddingRight: 4,
                }}
              >
                {!analysis || (analysis.messages || []).length === 0 ? (
                  <Alert
                    type="info"
                    showIcon
                    message="先执行分析，再通过对话要求 AI 补充、调整或重新梳理"
                  />
                ) : (
                  (analysis.messages || []).map((item, index) => (
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
              <TextArea
                rows={3}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="例如：把功能清单按模块重新梳理"
              />
              <Button
                type="primary"
                block
                style={{ marginTop: 8 }}
                icon={<SendOutlined />}
                loading={sendingChat}
                disabled={!analysis}
                onClick={handleSendChat}
              >
                发送并重新分析
              </Button>

              {history.length > 1 && (
                <div style={{ marginTop: 16 }}>
                  <Text type="secondary">历史分析</Text>
                  <Select
                    style={{ width: '100%', marginTop: 8 }}
                    value={analysis?.id}
                    onChange={(value) => {
                      const target = history.find((item) => item.id === value);
                      if (target) setAnalysis(target);
                    }}
                    options={history.map((item) => ({
                      label: `${new Date(item.created_at || '').toLocaleString()} · ${item.engine === 'llm' ? 'LLM' : '规则'}`,
                      value: item.id,
                    }))}
                  />
                </div>
              )}
            </Card>
          </Col>
        </Row>
      </Drawer>
    </div>
  );
}
