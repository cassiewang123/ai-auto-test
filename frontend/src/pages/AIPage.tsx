import { useState, useEffect } from 'react';
import {
  Card,
  Input,
  Button,
  Tabs,
  message,
  Tag,
  List,
  Space,
  Select,
  Radio,
  InputNumber,
  Table,
  Modal,
  Typography,
  Tooltip,
} from 'antd';
import {
  RobotOutlined,
  CodeOutlined,
  CheckCircleOutlined,
  BugOutlined,
  ThunderboltOutlined,
  ImportOutlined,
} from '@ant-design/icons';
import { aiApi, projectApi } from '../services/api';
import type { Project } from '../types';

const { TextArea } = Input;
const { Text } = Typography;

// 结构化用例的数据结构
interface StructuredCase {
  title: string;
  case_type?: string;
  priority?: string;
  method: string;
  url: string;
  headers?: Record<string, string>;
  params?: Record<string, any>;
  body?: any;
  assertions?: Array<{
    type?: string;
    assertion_type?: string;
    expression?: string;
    operator?: string;
    expected?: any;
  }>;
  description?: string;
}

export default function AIPage() {
  // 用例生成
  const [description, setDescription] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [generating, setGenerating] = useState(false);

  // 断言推荐
  const [responseJson, setResponseJson] = useState('');
  const [assertions, setAssertions] = useState<any[]>([]);
  const [recommending, setRecommending] = useState(false);

  // 失败分析
  const [failureInput, setFailureInput] = useState('');
  const [analysis, setAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);

  // 结构化用例生成
  const [sourceType, setSourceType] = useState<'interface' | 'har' | 'description'>('description');
  const [nlDescription, setNlDescription] = useState('');
  const [interfaceMethod, setInterfaceMethod] = useState('GET');
  const [interfaceUrl, setInterfaceUrl] = useState('/api/v1/endpoint');
  const [interfaceBody, setInterfaceBody] = useState('');
  const [harContent, setHarContent] = useState('');
  const [maxCases, setMaxCases] = useState(10);
  const [structuredCases, setStructuredCases] = useState<StructuredCase[]>([]);
  const [generatingStructured, setGeneratingStructured] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [targetProjectId, setTargetProjectId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [previewCase, setPreviewCase] = useState<StructuredCase | null>(null);

  useEffect(() => {
    projectApi.listAll().then((res) => {
      setProjects(res.data || []);
    }).catch(() => {});
  }, []);

  async function handleGenerate() {
    if (!description.trim()) {
      message.warning('请输入用例描述');
      return;
    }
    setGenerating(true);
    try {
      const res = await aiApi.generateTestCase({ description });
      setGeneratedCode(res.data?.code || '');
      message.success('生成成功');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleRecommend() {
    let sample: any;
    try {
      sample = responseJson ? JSON.parse(responseJson) : {};
    } catch {
      message.error('请输入有效的 JSON');
      return;
    }
    setRecommending(true);
    try {
      const res = await aiApi.recommendAssertions({ response_sample: sample });
      setAssertions(res.data?.assertions || []);
      message.success('推荐成功');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRecommending(false);
    }
  }

  async function handleAnalyze() {
    let result: any;
    try {
      result = failureInput ? JSON.parse(failureInput) : {};
    } catch {
      message.error('请输入有效的 JSON');
      return;
    }
    setAnalyzing(true);
    try {
      const res = await aiApi.analyzeFailure(result);
      setAnalysis(res.data);
      message.success('分析完成');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setAnalyzing(false);
    }
  }

  // 构造 source_data
  function buildSourceData(): Record<string, any> {
    if (sourceType === 'description') {
      return { description: nlDescription };
    }
    if (sourceType === 'interface') {
      let body: any = {};
      try {
        body = interfaceBody ? JSON.parse(interfaceBody) : {};
      } catch {
        // 忽略解析错误
      }
      return {
        method: interfaceMethod,
        url: interfaceUrl,
        body,
      };
    }
    // har
    return { har_content: harContent };
  }

  async function handleGenerateStructured() {
    if (sourceType === 'description' && !nlDescription.trim()) {
      message.warning('请输入用例描述');
      return;
    }
    if (sourceType === 'interface' && !interfaceUrl.trim()) {
      message.warning('请输入接口 URL');
      return;
    }
    if (sourceType === 'har' && !harContent.trim()) {
      message.warning('请粘贴 HAR 内容');
      return;
    }

    setGeneratingStructured(true);
    setStructuredCases([]);
    setSelectedRowKeys([]);
    try {
      const res = await aiApi.generateTestCases({
        source_type: sourceType,
        source_data: buildSourceData(),
        options: { max_cases: maxCases },
      });
      const cases = res.data?.cases || [];
      setStructuredCases(cases);
      // 默认全选
      setSelectedRowKeys(cases.map((_, idx) => idx));
      message.success(`已生成 ${cases.length} 条结构化用例`);
    } catch (e: any) {
      message.error(e.message || '生成失败');
    } finally {
      setGeneratingStructured(false);
    }
  }

  async function handleImport() {
    if (selectedRowKeys.length === 0) {
      message.warning('请至少选择一条用例');
      return;
    }
    const selectedCases = selectedRowKeys
      .map((k) => structuredCases[Number(k)])
      .filter(Boolean);
    setImporting(true);
    try {
      const res = await aiApi.importCases({
        cases: selectedCases,
        project_id: targetProjectId,
      });
      message.success(`成功导入 ${res.data?.created_count || 0} 条用例`);
      setStructuredCases([]);
      setSelectedRowKeys([]);
    } catch (e: any) {
      message.error(e.message || '导入失败');
    } finally {
      setImporting(false);
    }
  }

  // 结构化用例表格列
  const structuredColumns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      width: 200,
      render: (text: string, record: StructuredCase) => (
        <Tooltip title={record.description || text}>
          <a onClick={() => setPreviewCase(record)}>{text}</a>
        </Tooltip>
      ),
    },
    {
      title: '类型',
      dataIndex: 'case_type',
      key: 'case_type',
      width: 90,
      render: (v: string) => {
        const color = v === 'normal' ? 'green' : v === 'exception' ? 'red' : 'orange';
        return <Tag color={color}>{v || 'normal'}</Tag>;
      },
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 70,
      render: (v: string) => <Tag>{v || 'P1'}</Tag>,
    },
    {
      title: '方法',
      dataIndex: 'method',
      key: 'method',
      width: 70,
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
    },
    {
      title: '断言',
      key: 'assertions',
      width: 80,
      render: (_: any, record: StructuredCase) =>
        record.assertions?.length || 0,
    },
  ];

  return (
    <div>
      <Tabs
        items={[
          {
            key: 'generate',
            label: (
              <span>
                <CodeOutlined /> AI 用例生成
              </span>
            ),
            children: (
              <Card>
                <div style={{ marginBottom: 16 }}>
                  <TextArea
                    rows={4}
                    placeholder='输入自然语言描述，如："测试用户注册流程，覆盖正常注册、重复用户名、无效邮箱三种场景"'
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </div>
                <Button
                  type="primary"
                  icon={<RobotOutlined />}
                  loading={generating}
                  onClick={handleGenerate}
                >
                  生成测试用例
                </Button>
                {generatedCode && (
                  <div style={{ marginTop: 16 }}>
                    <pre
                      style={{
                        background: '#1a1a2e',
                        color: '#e2e8f0',
                        padding: 16,
                        borderRadius: 8,
                        overflow: 'auto',
                        fontSize: 13,
                        lineHeight: 1.6,
                        maxHeight: 500,
                      }}
                    >
                      <code>{generatedCode}</code>
                    </pre>
                  </div>
                )}
              </Card>
            ),
          },
          {
            key: 'structured',
            label: (
              <span>
                <ThunderboltOutlined /> AI 结构化用例生成
              </span>
            ),
            children: (
              <div>
                <Card title="步骤 1：选择数据源" style={{ marginBottom: 16 }}>
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Radio.Group
                      value={sourceType}
                      onChange={(e) => setSourceType(e.target.value)}
                    >
                      <Radio.Button value="description">自然语言描述</Radio.Button>
                      <Radio.Button value="interface">接口定义</Radio.Button>
                      <Radio.Button value="har">HAR 抓包</Radio.Button>
                    </Radio.Group>

                    {sourceType === 'description' && (
                      <TextArea
                        rows={4}
                        placeholder='输入需求描述，如："用户登录接口，覆盖正常登录、密码错误、账号不存在场景"'
                        value={nlDescription}
                        onChange={(e) => setNlDescription(e.target.value)}
                      />
                    )}

                    {sourceType === 'interface' && (
                      <Space wrap>
                        <Select
                          value={interfaceMethod}
                          onChange={setInterfaceMethod}
                          style={{ width: 100 }}
                          options={[
                            'GET', 'POST', 'PUT', 'PATCH', 'DELETE',
                          ].map((m) => ({ value: m, label: m }))}
                        />
                        <Input
                          style={{ width: 400 }}
                          placeholder="接口 URL，如 /api/v1/login"
                          value={interfaceUrl}
                          onChange={(e) => setInterfaceUrl(e.target.value)}
                        />
                        <TextArea
                          rows={3}
                          style={{ width: '100%' }}
                          placeholder='请求体 JSON（可选），如：{"username": "test", "password": "123"}'
                          value={interfaceBody}
                          onChange={(e) => setInterfaceBody(e.target.value)}
                        />
                      </Space>
                    )}

                    {sourceType === 'har' && (
                      <TextArea
                        rows={8}
                        placeholder='粘贴 HAR (HTTP Archive) JSON 内容'
                        value={harContent}
                        onChange={(e) => setHarContent(e.target.value)}
                      />
                    )}

                    <Space wrap>
                      <span>最大用例数：</span>
                      <InputNumber
                        min={1}
                        max={50}
                        value={maxCases}
                        onChange={(v) => setMaxCases(v || 10)}
                      />
                      <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        loading={generatingStructured}
                        onClick={handleGenerateStructured}
                      >
                        生成结构化用例
                      </Button>
                    </Space>
                  </Space>
                </Card>

                {structuredCases.length > 0 && (
                  <Card
                    title={
                      <Space>
                        <span>步骤 2：预览与选择</span>
                        <Tag color="blue">{structuredCases.length} 条</Tag>
                        <Tag color="cyan">已选 {selectedRowKeys.length} 条</Tag>
                      </Space>
                    }
                    extra={
                      <Space>
                        <Select
                          allowClear
                          placeholder="导入到项目（可选）"
                          style={{ width: 200 }}
                          value={targetProjectId || undefined}
                          onChange={(v) => setTargetProjectId(v || null)}
                          options={projects.map((p) => ({
                            value: p.id,
                            label: p.name,
                          }))}
                        />
                        <Button
                          type="primary"
                          icon={<ImportOutlined />}
                          loading={importing}
                          onClick={handleImport}
                          disabled={selectedRowKeys.length === 0}
                        >
                          导入选中用例
                        </Button>
                      </Space>
                    }
                  >
                    <Table
                      rowKey={(_, idx) => String(idx)}
                      columns={structuredColumns}
                      dataSource={structuredCases}
                      size="small"
                      pagination={false}
                      rowSelection={{
                        selectedRowKeys,
                        onChange: setSelectedRowKeys,
                      }}
                      expandable={{
                        expandedRowRender: (record: StructuredCase) => (
                          <div style={{ padding: '8px 0' }}>
                            <Space direction="vertical" style={{ width: '100%' }}>
                              {record.description && (
                                <Text type="secondary">描述: {record.description}</Text>
                              )}
                              <div>
                                <Text strong>请求头:</Text>
                                <pre style={{ fontSize: 12, margin: '4px 0' }}>
                                  {JSON.stringify(record.headers || {}, null, 2)}
                                </pre>
                              </div>
                              {record.body !== undefined && (
                                <div>
                                  <Text strong>请求体:</Text>
                                  <pre style={{ fontSize: 12, margin: '4px 0' }}>
                                    {JSON.stringify(record.body, null, 2)}
                                  </pre>
                                </div>
                              )}
                              <div>
                                <Text strong>断言规则:</Text>
                                <List
                                  size="small"
                                  dataSource={record.assertions || []}
                                  renderItem={(a, idx) => (
                                    <List.Item>
                                      <Space wrap>
                                        <Tag>{idx + 1}</Tag>
                                        <Tag color="cyan">{a.type || a.assertion_type}</Tag>
                                        {a.expression && <Tag>表达式: {a.expression}</Tag>}
                                        {a.operator && <Tag>操作符: {a.operator}</Tag>}
                                        {a.expected !== undefined && (
                                          <Tag>期望: {String(a.expected)}</Tag>
                                        )}
                                      </Space>
                                    </List.Item>
                                  )}
                                />
                              </div>
                            </Space>
                          </div>
                        ),
                      }}
                    />
                  </Card>
                )}

                <Modal
                  title={previewCase?.title}
                  open={!!previewCase}
                  onCancel={() => setPreviewCase(null)}
                  footer={null}
                  width={700}
                >
                  {previewCase && (
                    <div>
                      <Space wrap style={{ marginBottom: 12 }}>
                        <Tag color="blue">{previewCase.case_type || 'normal'}</Tag>
                        <Tag>{previewCase.priority || 'P1'}</Tag>
                        <Tag color="geekblue">{previewCase.method}</Tag>
                        <Tag>{previewCase.url}</Tag>
                      </Space>
                      {previewCase.description && (
                        <p style={{ color: '#888' }}>{previewCase.description}</p>
                      )}
                      <pre
                        style={{
                          background: '#1a1a2e',
                          color: '#e2e8f0',
                          padding: 12,
                          borderRadius: 6,
                          fontSize: 12,
                          maxHeight: 400,
                          overflow: 'auto',
                        }}
                      >
                        {JSON.stringify(previewCase, null, 2)}
                      </pre>
                    </div>
                  )}
                </Modal>
              </div>
            ),
          },
          {
            key: 'assertions',
            label: (
              <span>
                <CheckCircleOutlined /> AI 断言推荐
              </span>
            ),
            children: (
              <Card>
                <div style={{ marginBottom: 16 }}>
                  <TextArea
                    rows={6}
                    placeholder='粘贴接口响应 JSON，如：{"code": 0, "data": {"id": 1, "name": "Ada"}}'
                    value={responseJson}
                    onChange={(e) => setResponseJson(e.target.value)}
                  />
                </div>
                <Button
                  type="primary"
                  icon={<RobotOutlined />}
                  loading={recommending}
                  onClick={handleRecommend}
                >
                  推荐断言规则
                </Button>
                {assertions.length > 0 && (
                  <List
                    style={{ marginTop: 16 }}
                    bordered
                    dataSource={assertions}
                    renderItem={(a, idx) => (
                      <List.Item>
                        <Space wrap>
                          <Tag color="blue">{idx + 1}</Tag>
                          <Tag color="cyan">{a.assertion_type || a.type}</Tag>
                          {a.expression && (
                            <Tag>表达式: {a.expression}</Tag>
                          )}
                          {a.operator && <Tag>操作符: {a.operator}</Tag>}
                          {a.expected !== undefined && (
                            <Tag>期望: {String(a.expected)}</Tag>
                          )}
                        </Space>
                      </List.Item>
                    )}
                  />
                )}
              </Card>
            ),
          },
          {
            key: 'analyze',
            label: (
              <span>
                <BugOutlined /> AI 失败分析
              </span>
            ),
            children: (
              <Card>
                <div style={{ marginBottom: 16 }}>
                  <TextArea
                    rows={8}
                    placeholder='粘贴失败用例的 ExecutionResult JSON，包含 request/response/error_message 等字段'
                    value={failureInput}
                    onChange={(e) => setFailureInput(e.target.value)}
                  />
                </div>
                <Button
                  type="primary"
                  icon={<RobotOutlined />}
                  loading={analyzing}
                  onClick={handleAnalyze}
                >
                  分析失败原因
                </Button>
                {analysis && (
                  <Card
                    type="inner"
                    title="分析结果"
                    style={{ marginTop: 16 }}
                  >
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>
                        <Tag color="red">根因</Tag>
                        {analysis.root_cause || '-'}
                      </div>
                      <div>
                        <Tag color="orange">证据</Tag>
                        {analysis.evidence || '-'}
                      </div>
                      <div>
                        <Tag color="blue">分类</Tag>
                        {analysis.category || '-'}
                      </div>
                      <div>
                        <Tag color="green">建议</Tag>
                        {analysis.suggestion || '-'}
                      </div>
                      {analysis.confidence !== undefined && (
                        <div>
                          <Tag>置信度</Tag>
                          {(analysis.confidence * 100).toFixed(0)}%
                        </div>
                      )}
                    </Space>
                  </Card>
                )}
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
