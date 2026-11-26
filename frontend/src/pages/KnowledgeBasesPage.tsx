import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  BookOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { knowledgeBaseApi } from '../services/api';
import {
  DOCUMENT_ACCEPT_PATTERN,
  DOCUMENT_SUPPORT_HINT,
} from '../utils/documentTypes';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type KnowledgeBase = {
  id: string;
  name: string;
  description?: string | null;
  chunk_strategy: string;
  chunk_size: number;
  chunk_overlap: number;
  document_count?: number;
  chunk_count?: number;
};

type KnowledgeDocument = {
  id: string;
  filename: string;
  category?: string | null;
  file_type: string;
  file_size: number;
  status: string;
  error_message?: string | null;
  chunk_count: number;
  warnings?: string[];
  created_at?: string;
};

type RetrievalHit = {
  chunk_id: string;
  document_name: string;
  chunk_index: number;
  heading?: string | null;
  content: string;
  score: number;
};

const STRATEGY_OPTIONS = [
  { label: '精细（按标题）', value: 'heading' },
  { label: '标准（固定窗口）', value: 'fixed_window' },
  { label: '按段落', value: 'paragraph' },
];

const ACCEPT_PATTERN = DOCUMENT_ACCEPT_PATTERN;

const STATUS_COLOR: Record<string, string> = {
  indexed: 'success',
  pending: 'processing',
  failed: 'error',
};

const STATUS_LABEL: Record<string, string> = {
  indexed: '已索引',
  pending: '待索引',
  failed: '索引失败',
};

function formatBytes(size: number): string {
  if (!size) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export default function KnowledgeBasesPage() {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [basesLoading, setBasesLoading] = useState(false);
  const [activeBaseId, setActiveBaseId] = useState<string | undefined>();
  const activeBase = bases.find((item) => item.id === activeBaseId);

  const [tab, setTab] = useState('documents');
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const [settingsForm] = Form.useForm();
  const [savingSettings, setSavingSettings] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<any>(null);

  const [retrieveQuery, setRetrieveQuery] = useState('');
  const [retrieving, setRetrieving] = useState(false);
  const [retrieveResult, setRetrieveResult] = useState<any>(null);

  const [chunkModal, setChunkModal] = useState<{ open: boolean; title: string }>({
    open: false,
    title: '',
  });
  const [chunks, setChunks] = useState<any[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunkDocId, setChunkDocId] = useState<string | undefined>();

  const loadBases = useCallback(async () => {
    setBasesLoading(true);
    try {
      const res = await knowledgeBaseApi.list({ page: 1, page_size: 100 });
      const items: KnowledgeBase[] = res.data || [];
      setBases(items);
      setActiveBaseId((current) => {
        if (current && items.some((item) => item.id === current)) return current;
        return items[0]?.id;
      });
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBasesLoading(false);
    }
  }, []);

  const loadDocuments = useCallback(async (baseId: string) => {
    setDocumentsLoading(true);
    try {
      const res = await knowledgeBaseApi.listDocuments(baseId, {
        page: 1,
        page_size: 100,
      });
      setDocuments(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setDocumentsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBases();
  }, [loadBases]);

  useEffect(() => {
    if (activeBaseId) {
      loadDocuments(activeBaseId);
      setRetrieveResult(null);
      setRetrieveQuery('');
    } else {
      setDocuments([]);
    }
  }, [activeBaseId, loadDocuments]);

  useEffect(() => {
    if (!activeBase) return;
    settingsForm.setFieldsValue({
      name: activeBase.name,
      description: activeBase.description || '',
      chunk_strategy: activeBase.chunk_strategy,
      chunk_size: activeBase.chunk_size,
      chunk_overlap: activeBase.chunk_overlap,
    });
  }, [activeBase, settingsForm]);

  async function handleCreate() {
    const values = await createForm.validateFields();
    setCreating(true);
    try {
      const res = await knowledgeBaseApi.create(values);
      message.success('知识库已创建');
      setCreateOpen(false);
      createForm.resetFields();
      await loadBases();
      if (res.data?.id) setActiveBaseId(res.data.id);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteBase(id: string) {
    try {
      await knowledgeBaseApi.remove(id);
      message.success('知识库已删除');
      await loadBases();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleUpload(file: File) {
    if (!activeBaseId) return false;
    setUploading(true);
    try {
      const res = await knowledgeBaseApi.uploadDocument(activeBaseId, file);
      const uploaded = res.data;
      if (uploaded?.status === 'failed') {
        message.warning(uploaded.error_message || '文档未建立索引');
      } else if (uploaded?.warnings?.length) {
        message.warning(uploaded.warnings[0]);
      } else {
        message.success(`${file.name} 已索引 ${uploaded.chunk_count} 个分块`);
      }
      await Promise.all([loadDocuments(activeBaseId), loadBases()]);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setUploading(false);
    }
    return false;
  }

  async function handleDeleteDocument(documentId: string) {
    if (!activeBaseId) return;
    try {
      await knowledgeBaseApi.deleteDocument(activeBaseId, documentId);
      message.success('文档已删除');
      await Promise.all([loadDocuments(activeBaseId), loadBases()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleReindex(documentId: string) {
    if (!activeBaseId) return;
    try {
      const res = await knowledgeBaseApi.reindexDocument(activeBaseId, documentId);
      message.success(`已重建索引，共 ${res.data?.chunk_count ?? 0} 个分块`);
      await Promise.all([loadDocuments(activeBaseId), loadBases()]);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function openChunks(document: KnowledgeDocument) {
    if (!activeBaseId) return;
    setChunkDocId(document.id);
    setChunkModal({ open: true, title: `分块：${document.filename}` });
    setChunksLoading(true);
    try {
      const res = await knowledgeBaseApi.listChunks(activeBaseId, document.id, {
        page: 1,
        page_size: 100,
      });
      setChunks(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setChunksLoading(false);
    }
  }

  async function handleSaveSettings(rebuild: boolean) {
    if (!activeBaseId) return;
    const values = await settingsForm.validateFields();
    setSavingSettings(true);
    try {
      await knowledgeBaseApi.update(activeBaseId, values);
      message.success('设置已保存');
      await loadBases();
      if (rebuild) {
        setRebuilding(true);
        const res = await knowledgeBaseApi.rebuildIndex(activeBaseId);
        message.success(
          `已重建 ${res.data?.chunk_count ?? 0} 个分块（${res.data?.document_count ?? 0} 份文档）`
        );
        await Promise.all([loadDocuments(activeBaseId), loadBases()]);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSavingSettings(false);
      setRebuilding(false);
    }
  }

  async function handlePreview() {
    const values = await settingsForm.validateFields();
    if (!activeBase?.description && documents.length === 0) {
      message.info('可上传文档后在实际内容上验证分块效果');
    }
    const sample =
      documents.length > 0
        ? undefined
        : '第一段内容：用户登录需要校验用户名与密码。\n\n第二段内容：验证码有效期 60 秒。';
    if (sample) {
      setPreviewing(true);
      try {
        const res = await knowledgeBaseApi.previewChunks({
          text: sample,
          chunk_strategy: values.chunk_strategy,
          chunk_size: values.chunk_size,
          chunk_overlap: values.chunk_overlap,
        });
        setPreview(res.data);
      } catch (e: any) {
        message.error(e.message);
      } finally {
        setPreviewing(false);
      }
      return;
    }
    // 有文档时直接重建索引预览（不落库）
    message.info('请使用「保存并重建索引」查看实际分块结果');
  }

  async function handleRetrieve() {
    if (!activeBaseId || !retrieveQuery.trim()) {
      message.warning('请输入检索内容');
      return;
    }
    setRetrieving(true);
    try {
      const res = await knowledgeBaseApi.retrieve(activeBaseId, {
        query: retrieveQuery.trim(),
        top_k: 5,
      });
      setRetrieveResult(res.data);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRetrieving(false);
    }
  }

  const documentColumns = [
    { title: '文件名', dataIndex: 'filename', ellipsis: true },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (value: string | null) => value || '未分类',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string, record: KnowledgeDocument) => (
        <Space direction="vertical" size={0}>
          <Tag color={STATUS_COLOR[value] || 'default'}>
            {STATUS_LABEL[value] || value}
          </Tag>
          {record.warnings && record.warnings.length > 0 && (
            <Text type="warning" style={{ fontSize: 12 }}>
              {record.warnings[0]}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      width: 100,
      render: (value: number) => formatBytes(value),
    },
    {
      title: '分块',
      dataIndex: 'chunk_count',
      width: 80,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => (value ? new Date(value).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 240,
      render: (_: unknown, record: KnowledgeDocument) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openChunks(record)}>
            查看分块
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SyncOutlined />}
            onClick={() => handleReindex(record.id)}
          >
            重建索引
          </Button>
          <Popconfirm
            title="确认删除该文档？"
            onConfirm={() => handleDeleteDocument(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card
          size="small"
          title={
            <Space>
              <BookOutlined />
              <span>知识库</span>
            </Space>
          }
          extra={
            <Button
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => setCreateOpen(true)}
            >
              新建
            </Button>
          }
          loading={basesLoading}
        >
          {bases.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="还没有知识库"
            />
          ) : (
            <List
              dataSource={bases}
              renderItem={(item) => (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    background:
                      item.id === activeBaseId ? 'rgba(22,119,255,0.08)' : undefined,
                    borderRadius: 6,
                    paddingInline: 8,
                  }}
                  onClick={() => setActiveBaseId(item.id)}
                  actions={[
                    <Popconfirm
                      key="delete"
                      title="确认删除知识库及其文档？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        handleDeleteBase(item.id);
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
                    title={item.name}
                    description={
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {item.document_count || 0} 份文档 · {item.chunk_count || 0} 个分块
                      </Text>
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
              <DatabaseOutlined />
              <span>{activeBase?.name || '请选择知识库'}</span>
            </Space>
          }
          extra={
            activeBaseId && (
              <Upload
                accept={ACCEPT_PATTERN}
                showUploadList={false}
                beforeUpload={handleUpload}
                disabled={uploading}
              >
                <Tooltip title={DOCUMENT_SUPPORT_HINT}>
                  <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
                    上传文档
                  </Button>
                </Tooltip>
              </Upload>
            )
          }
        >
          {!activeBaseId ? (
            <Empty description="请先创建或选择左侧的知识库" />
          ) : (
            <>
              <Row gutter={16} style={{ marginBottom: 12 }}>
                <Col span={8}>
                  <Statistic title="文档数" value={activeBase?.document_count || 0} />
                </Col>
                <Col span={8}>
                  <Statistic title="分块数" value={activeBase?.chunk_count || 0} />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="分块参数"
                    value={`${activeBase?.chunk_size} / ${activeBase?.chunk_overlap}`}
                    suffix={
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        大/重叠
                      </Text>
                    }
                  />
                </Col>
              </Row>

              <Tabs
                activeKey={tab}
                onChange={setTab}
                items={[
                  {
                    key: 'documents',
                    label: '文档',
                    children: (
                      <Table
                        rowKey="id"
                        size="small"
                        loading={documentsLoading}
                        dataSource={documents}
                        columns={documentColumns}
                        pagination={{ pageSize: 10, showSizeChanger: false }}
                      />
                    ),
                  },
                  {
                    key: 'retrieve',
                    label: (
                      <span>
                        <FileSearchOutlined /> 试检索
                      </span>
                    ),
                    children: (
                      <div>
                        <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
                          <Input
                            value={retrieveQuery}
                            onChange={(e) => setRetrieveQuery(e.target.value)}
                            onPressEnter={handleRetrieve}
                            placeholder="输入检索内容，验证分块粒度与召回效果"
                          />
                          <Button
                            type="primary"
                            icon={<SearchOutlined />}
                            loading={retrieving}
                            onClick={handleRetrieve}
                          >
                            检索
                          </Button>
                        </Space.Compact>

                        {!retrieveResult ? (
                          <Alert
                            type="info"
                            showIcon
                            message="检索基于分块关键词打分，无向量依赖、离线可用"
                          />
                        ) : retrieveResult.hit_count === 0 ? (
                          <Empty description="没有命中分块，可尝试调整分块参数或补充文档" />
                        ) : (
                          <>
                            <Text type="secondary">
                              命中 {retrieveResult.hit_count} 个分块，最高相关度{' '}
                              {retrieveResult.top_score}
                              {retrieveResult.query_tokens?.length > 0 &&
                                ` · 检索词：${retrieveResult.query_tokens.join('、')}`}
                            </Text>
                            <List
                              style={{ marginTop: 8 }}
                              dataSource={retrieveResult.hits as RetrievalHit[]}
                              renderItem={(hit) => (
                                <List.Item>
                                  <List.Item.Meta
                                    title={
                                      <Space>
                                        <Tag color="blue">
                                          {Math.round(hit.score * 100)}%
                                        </Tag>
                                        <span>
                                          {hit.document_name} · 分块 {hit.chunk_index}
                                        </span>
                                        {hit.heading && <Tag>{hit.heading}</Tag>}
                                      </Space>
                                    }
                                    description={
                                      <Paragraph
                                        ellipsis={{ rows: 4, expandable: true }}
                                        style={{ marginBottom: 0 }}
                                      >
                                        {hit.content}
                                      </Paragraph>
                                    }
                                  />
                                </List.Item>
                              )}
                            />
                          </>
                        )}
                      </div>
                    ),
                  },
                  {
                    key: 'settings',
                    label: (
                      <span>
                        <SettingOutlined /> 设置
                      </span>
                    ),
                    children: (
                      <Form form={settingsForm} layout="vertical">
                        <Form.Item name="name" label="名称">
                          <Input />
                        </Form.Item>
                        <Form.Item name="description" label="说明">
                          <TextArea rows={2} placeholder="简要描述该知识库用途" />
                        </Form.Item>
                        <Collapse
                          defaultActiveKey={['chunk']}
                          items={[
                            {
                              key: 'chunk',
                              label: '高级：分段',
                              children: (
                                <>
                                  <Form.Item name="chunk_strategy" label="分段方式">
                                    <Radio.Group options={STRATEGY_OPTIONS} />
                                  </Form.Item>
                                  <Form.Item
                                    name="chunk_size"
                                    label="分块大小"
                                    extra="建议 400-1500。过小检索碎片化，过大上下文噪声多"
                                    rules={[{ required: true }]}
                                  >
                                    <InputNumber min={100} max={4000} style={{ width: '100%' }} />
                                  </Form.Item>
                                  <Form.Item
                                    name="chunk_overlap"
                                    label="分块重叠"
                                    extra="须小于分块大小，用于保留跨段语义"
                                    rules={[{ required: true }]}
                                  >
                                    <InputNumber min={0} max={4000} style={{ width: '100%' }} />
                                  </Form.Item>
                                </>
                              ),
                            },
                          ]}
                        />
                        <Space style={{ marginTop: 12 }}>
                          <Button
                            type="primary"
                            loading={savingSettings && !rebuilding}
                            onClick={() => handleSaveSettings(false)}
                          >
                            保存
                          </Button>
                          <Button
                            loading={rebuilding}
                            icon={<SyncOutlined />}
                            onClick={() => handleSaveSettings(true)}
                          >
                            保存并重建索引
                          </Button>
                          <Button
                            loading={previewing}
                            onClick={handlePreview}
                            icon={<ReloadOutlined />}
                          >
                            分块预览
                          </Button>
                          <Popconfirm
                            title="确认删除该知识库？"
                            onConfirm={() => handleDeleteBase(activeBaseId)}
                          >
                            <Button danger>删除知识库</Button>
                          </Popconfirm>
                        </Space>

                        {preview && (
                          <Card
                            size="small"
                            title={`分块预览（共 ${preview.chunk_count} 个分块）`}
                            style={{ marginTop: 12 }}
                          >
                            <Collapse
                              items={(preview.chunks || []).map((chunk: any) => ({
                                key: String(chunk.index),
                                label: `#${chunk.index} · ${chunk.char_count} 字符${
                                  chunk.heading ? ` · ${chunk.heading}` : ''
                                }`,
                                children: (
                                  <Paragraph
                                    style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}
                                  >
                                    {chunk.content}
                                  </Paragraph>
                                ),
                              }))}
                            />
                          </Card>
                        )}
                      </Form>
                    ),
                  },
                ]}
              />
            </>
          )}
        </Card>
      </Col>

      <Modal
        title="新建知识库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={creating}
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{
            chunk_strategy: 'fixed_window',
            chunk_size: 400,
            chunk_overlap: 80,
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入知识库名称' }]}
          >
            <Input placeholder="例如：Rain 测试平台" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <TextArea rows={2} placeholder="存放哪些技术/业务文档" />
          </Form.Item>
          <Form.Item name="chunk_strategy" label="分段方式">
            <Select options={STRATEGY_OPTIONS} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="chunk_size" label="分块大小" rules={[{ required: true }]}>
                <InputNumber min={100} max={4000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="chunk_overlap" label="分块重叠" rules={[{ required: true }]}>
                <InputNumber min={0} max={4000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title={chunkModal.title}
        open={chunkModal.open}
        onCancel={() => setChunkModal({ open: false, title: '' })}
        footer={null}
        width={860}
      >
        <div style={{ maxHeight: 560, overflow: 'auto' }}>
          {chunksLoading ? (
            <Empty description="加载中" />
          ) : chunks.length === 0 ? (
            <Empty description="该文档没有分块" />
          ) : (
            <Collapse
              items={chunks.map((chunk) => ({
                key: chunk.id,
                label: `#${chunk.chunk_index} 已写入 · ${chunk.char_count} 字符${
                  chunk.heading ? ` · ${chunk.heading}` : ''
                }`,
                children: (
                  <>
                    <Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                      {chunk.content}
                    </Paragraph>
                    {chunk.keywords?.length > 0 && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        关键词：{chunk.keywords.slice(0, 12).join('、')}
                      </Text>
                    )}
                  </>
                ),
              }))}
            />
          )}
        </div>
        {chunkDocId && (
          <Button
            style={{ marginTop: 12 }}
            icon={<SyncOutlined />}
            onClick={async () => {
              await handleReindex(chunkDocId);
              if (activeBaseId) {
                const res = await knowledgeBaseApi.listChunks(activeBaseId, chunkDocId, {
                  page: 1,
                  page_size: 100,
                });
                setChunks(res.data || []);
              }
            }}
          >
            重建该文档索引
          </Button>
        )}
      </Modal>
    </Row>
  );
}
