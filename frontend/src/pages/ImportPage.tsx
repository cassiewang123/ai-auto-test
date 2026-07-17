import { useEffect, useState, type Key } from 'react';
import {
  Card,
  Input,
  Button,
  Space,
  message,
  Table,
  Tag,
  Tabs,
  Modal,
  Alert,
  Spin,
  Empty,
  Row,
  Col,
  Statistic,
  Select,
  Form,
  Upload,
} from 'antd';
import {
  ImportOutlined,
  EyeOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  PlusOutlined,
  InboxOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { importApi, captureApi, projectApi } from '../services/api';
import type { ImportedEndpoint, CapturedEndpoint } from '../services/api';
import type { Project, ProjectCreate } from '../types';

const { TextArea } = Input;

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
};

export default function ImportPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('url');
  const [url, setUrl] = useState('http://localhost:8000/api/v1/openapi.json');
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000');
  const [pathPrefix, setPathPrefix] = useState('');
  const [specJson, setSpecJson] = useState('');
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [endpoints, setEndpoints] = useState<ImportedEndpoint[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<Key[]>([]);
  const [hasPreviewed, setHasPreviewed] = useState(false);

  // 页面抓取相关状态
  const [scanUrl, setScanUrl] = useState('http://robin.ep.local:30080/swgd-imap-operation-ui/');
  const [scanBaseUrl, setScanBaseUrl] = useState('http://robin.ep.local:30080');
  const [scanProjectId, setScanProjectId] = useState<string | undefined>(undefined);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanImporting, setScanImporting] = useState(false);
  const [scanEndpoints, setScanEndpoints] = useState<CapturedEndpoint[]>([]);
  const [scanSelectedKeys, setScanSelectedKeys] = useState<Key[]>([]);
  const [scanHasResults, setScanHasResults] = useState(false);

  // HAR 抓包导入相关状态
  const [harContent, setHarContent] = useState<any>(null);
  const [harFileName, setHarFileName] = useState('');
  const [harDomainFilter, setHarDomainFilter] = useState('');
  const [harMethodFilter, setHarMethodFilter] = useState<string | undefined>(undefined);
  const [harLoading, setHarLoading] = useState(false);
  const [harImporting, setHarImporting] = useState(false);
  const [harInterfaces, setHarInterfaces] = useState<any[]>([]);
  const [harSelectedKeys, setHarSelectedKeys] = useState<Key[]>([]);
  const [harHasResults, setHarHasResults] = useState(false);

  // 项目相关
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [projectForm] = Form.useForm<ProjectCreate>();

  async function loadProjects() {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  async function handlePreview() {
    setLoading(true);
    setEndpoints([]);
    setSelectedKeys([]);
    setHasPreviewed(false);
    try {
      const data: any = { base_url: baseUrl, path_prefix: pathPrefix };
      if (activeTab === 'url') {
        if (!url.trim()) {
          message.warning('请输入 OpenAPI 文档 URL');
          setLoading(false);
          return;
        }
        data.url = url.trim();
      } else {
        if (!specJson.trim()) {
          message.warning('请粘贴 OpenAPI JSON');
          setLoading(false);
          return;
        }
        try {
          data.spec = JSON.parse(specJson);
        } catch {
          message.error('JSON 格式不正确');
          setLoading(false);
          return;
        }
      }

      const res = await importApi.preview(data);
      if (res.data.error) {
        message.error(res.data.error);
      } else {
        setEndpoints(res.data.endpoints || []);
        setSelectedKeys(res.data.endpoints.map((_, i) => i));
        setHasPreviewed(true);
        message.success(`解析到 ${res.data.total} 个接口`);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleImport() {
    if (selectedKeys.length === 0) {
      message.warning('请至少选择一个接口');
      return;
    }
    setImporting(true);
    try {
      const data: any = {
        base_url: baseUrl,
        path_prefix: pathPrefix,
        preview_only: false,
      };
      if (activeTab === 'url') {
        data.url = url.trim();
      } else {
        data.spec = JSON.parse(specJson);
      }

      const res = await importApi.importOpenapi(data);
      if (res.data.error) {
        message.error(res.data.error);
      } else {
        message.success(`成功导入 ${res.data.created} 个测试用例`);
        Modal.success({
          title: '导入完成',
          content: (
            <div>
              <p>共解析 {res.data.total} 个接口</p>
              <p>成功创建 {res.data.created} 个测试用例</p>
              <p style={{ marginTop: 16 }}>
                你现在可以前往接口列表查看，或在快速测试中执行它们。
              </p>
            </div>
          ),
          onOk: () => navigate('/api-list'),
        });
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setImporting(false);
    }
  }

  // 页面抓取：扫描
  async function handleScan() {
    if (!scanUrl.trim()) {
      message.warning('请输入要抓取的页面 URL');
      return;
    }
    setScanLoading(true);
    setScanEndpoints([]);
    setScanSelectedKeys([]);
    setScanHasResults(false);
    try {
      const res = await captureApi.scan({
        url: scanUrl.trim(),
        base_url: scanBaseUrl || undefined,
      });
      if (res.data.error) {
        message.error(res.data.error);
      } else {
        setScanEndpoints(res.data.endpoints || []);
        setScanSelectedKeys((res.data.endpoints || []).map((_, i) => i));
        setScanHasResults(true);
        message.success(`扫描到 ${res.data.total} 个接口`);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setScanLoading(false);
    }
  }

  // 页面抓取：导入
  async function handleCaptureImport() {
    if (scanSelectedKeys.length === 0) {
      message.warning('请至少选择一个接口');
      return;
    }
    if (!scanProjectId) {
      message.warning('请选择要导入到的项目');
      return;
    }
    setScanImporting(true);
    try {
      const selected = scanSelectedKeys.map((k) => scanEndpoints[k as number]);
      const res = await captureApi.import({
        project_id: scanProjectId,
        base_url: scanBaseUrl || undefined,
        endpoints: selected,
      });
      message.success(`成功导入 ${res.data.created} 个接口`);
      Modal.success({
        title: '导入完成',
        content: (
          <div>
            <p>共解析 {res.data.total} 个接口</p>
            <p>成功创建 {res.data.created} 个测试用例</p>
          </div>
        ),
        onOk: () => navigate('/api-list'),
      });
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setScanImporting(false);
    }
  }

  // HAR 抓包：预览解析
  async function handleHarPreview() {
    if (!harContent) {
      message.warning('请先上传 HAR 文件');
      return;
    }
    setHarLoading(true);
    setHarInterfaces([]);
    setHarSelectedKeys([]);
    setHarHasResults(false);
    try {
      const res = await importApi.previewHar({
        har_content: harContent,
        domain_filter: harDomainFilter || undefined,
        method_filter: harMethodFilter || undefined,
      });
      if (res.data.error) {
        message.error(res.data.error);
      } else {
        setHarInterfaces(res.data.interfaces || []);
        setHarSelectedKeys((res.data.interfaces || []).map((_, i) => i));
        setHarHasResults(true);
        message.success(`解析到 ${res.data.total} 个接口`);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setHarLoading(false);
    }
  }

  // HAR 抓包：导入选中的接口
  async function handleHarImport() {
    if (harSelectedKeys.length === 0) {
      message.warning('请至少选择一个接口');
      return;
    }
    setHarImporting(true);
    try {
      // 传入选中的接口完整对象（后端需要完整字段来创建用例）
      const selected = harSelectedKeys.map((k) => harInterfaces[k as number]);
      const res = await importApi.importHar({
        selected_interfaces: selected,
      });
      message.success(`成功导入 ${res.data.created_count} 个测试用例`);
      Modal.success({
        title: '导入完成',
        content: (
          <div>
            <p>成功创建 {res.data.created_count} 个测试用例</p>
            <p style={{ marginTop: 16 }}>
              你现在可以前往接口列表查看，或在快速测试中执行它们。
            </p>
          </div>
        ),
        onOk: () => navigate('/api-list'),
      });
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setHarImporting(false);
    }
  }

  // 新建项目
  async function handleCreateProject() {
    try {
      const values = await projectForm.validateFields();
      setCreatingProject(true);
      const res = await projectApi.create(values);
      message.success('项目创建成功');
      setProjectModalOpen(false);
      projectForm.resetFields();
      await loadProjects();
      if (res.data?.id) setScanProjectId(res.data.id);
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setCreatingProject(false);
    }
  }

  // 统计信息
  const methodStats = endpoints.reduce((acc, ep) => {
    acc[ep.method] = (acc[ep.method] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div>
      <Card
        title={
          <Space>
            <ImportOutlined />
            <span>接口导入</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              从 OpenAPI/Swagger 文档或页面抓取自动解析接口并生成测试用例
            </span>
          </Space>
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'url',
              label: '从 URL 导入',
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    title="输入 OpenAPI/Swagger 文档的 JSON URL，系统将自动解析所有接口"
                    description={
                      <span>
                        当前项目的 API 文档地址通常是：
                        <code style={{ background: '#f3f4f6', padding: '2px 6px', borderRadius: 4 }}>
                          http://localhost:8000/api/v1/openapi.json
                        </code>
                      </span>
                    }
                  />
                  <Space style={{ width: '100%', marginBottom: 16 }} size="middle">
                    <Input
                      placeholder="OpenAPI JSON URL"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      style={{ width: 500 }}
                    />
                  </Space>
                </div>
              ),
            },
            {
              key: 'json',
              label: '粘贴 JSON',
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    title="直接粘贴 OpenAPI/Swagger 的 JSON 内容"
                  />
                  <TextArea
                    rows={10}
                    placeholder='{"openapi": "3.0.0", "paths": {"/api/v1/users": {"get": {...}}}, ...}'
                    value={specJson}
                    onChange={(e) => setSpecJson(e.target.value)}
                  />
                </div>
              ),
            },
            {
              key: 'capture',
              label: '页面抓取',
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    title="输入页面地址，系统将扫描页面并提取其中的 API 接口"
                    description="适用于抓取前端页面（如后台管理系统）中调用的所有接口。"
                  />
                  <Row gutter={16}>
                    <Col xs={24} md={12}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                        页面 URL
                      </label>
                      <Input
                        value={scanUrl}
                        onChange={(e) => setScanUrl(e.target.value)}
                        placeholder="http://robin.ep.local:30080/swgd-imap-operation-ui/"
                      />
                    </Col>
                    <Col xs={24} md={12}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                        Base URL（接口地址前缀）
                      </label>
                      <Input
                        value={scanBaseUrl}
                        onChange={(e) => setScanBaseUrl(e.target.value)}
                        placeholder="http://robin.ep.local:30080"
                      />
                    </Col>
                  </Row>
                  <Row gutter={16} style={{ marginTop: 16 }}>
                    <Col xs={24} md={16}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                        导入到项目
                      </label>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <Select
                          value={scanProjectId}
                          onChange={(v) => setScanProjectId(v)}
                          placeholder="选择要导入到的项目"
                          showSearch
                          optionFilterProp="label"
                          style={{ flex: 1 }}
                          options={projects.map((p) => ({ value: p.id, label: p.name }))}
                        />
                        <Button icon={<PlusOutlined />} onClick={() => setProjectModalOpen(true)}>
                          新建项目
                        </Button>
                      </div>
                    </Col>
                    <Col
                      xs={24}
                      md={8}
                      style={{ display: 'flex', alignItems: 'flex-end' }}
                    >
                      <Button
                        type="primary"
                        icon={<SearchOutlined />}
                        loading={scanLoading}
                        onClick={handleScan}
                        size="large"
                      >
                        开始扫描
                      </Button>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'har',
              label: 'HAR 抓包导入',
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    title="上传浏览器导出的 HAR 抓包文件，系统将解析其中的接口请求"
                    description="在浏览器 DevTools 的 Network 面板中，右键选择「Save all as HAR with content」导出 .har 文件。"
                  />
                  <Upload.Dragger
                    accept=".har"
                    maxCount={1}
                    beforeUpload={(file) => {
                      const reader = new FileReader();
                      reader.onload = (e) => {
                        try {
                          const content = JSON.parse(e.target?.result as string);
                          setHarContent(content);
                          setHarFileName(file.name);
                          // 重置之前的预览结果
                          setHarInterfaces([]);
                          setHarSelectedKeys([]);
                          setHarHasResults(false);
                          message.success(`已加载文件：${file.name}`);
                        } catch {
                          message.error('HAR 文件解析失败，请确认是合法的 JSON 格式');
                        }
                      };
                      reader.readAsText(file);
                      return false; // 阻止自动上传
                    }}
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">点击或拖拽 HAR 文件到此区域上传</p>
                    <p className="ant-upload-hint">支持单个 .har 文件，文件需为 JSON 格式</p>
                  </Upload.Dragger>
                  {harFileName && (
                    <div style={{ marginTop: 8, color: '#6b7280' }}>
                      已加载文件：<Tag color="blue">{harFileName}</Tag>
                    </div>
                  )}
                  <Row gutter={16} style={{ marginTop: 16 }}>
                    <Col xs={24} sm={12} md={8}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                        域名/URL 筛选（可选）
                      </label>
                      <Input
                        value={harDomainFilter}
                        onChange={(e) => setHarDomainFilter(e.target.value)}
                        placeholder="如 example.com（仅保留包含该串的接口）"
                      />
                    </Col>
                    <Col xs={24} sm={12} md={8}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                        请求方法筛选（可选）
                      </label>
                      <Select
                        value={harMethodFilter}
                        onChange={(v) => setHarMethodFilter(v)}
                        placeholder="如 GET（仅保留该方法的接口）"
                        allowClear
                        style={{ width: '100%' }}
                        options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => ({
                          value: m,
                          label: m,
                        }))}
                      />
                    </Col>
                    <Col
                      xs={24}
                      md={8}
                      style={{ display: 'flex', alignItems: 'flex-end' }}
                    >
                      <Button
                        type="primary"
                        icon={<EyeOutlined />}
                        loading={harLoading}
                        onClick={handleHarPreview}
                        size="large"
                        disabled={!harContent}
                      >
                        预览解析结果
                      </Button>
                    </Col>
                  </Row>
                </div>
              ),
            },
          ]}
        />

        {/* 通用配置：仅 OpenAPI 导入使用 */}
        {(activeTab === 'url' || activeTab === 'json') && (
          <Row gutter={16} style={{ marginBottom: 16, marginTop: 16 }}>
            <Col xs={24} sm={12} md={8}>
              <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                Base URL（请求地址前缀）
              </label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:8000"
              />
            </Col>
            <Col xs={24} sm={12} md={8}>
              <label style={{ fontWeight: 600, display: 'block', marginBottom: 4 }}>
                路径前缀筛选（可选）
              </label>
              <Input
                value={pathPrefix}
                onChange={(e) => setPathPrefix(e.target.value)}
                placeholder="如 /api/v1（仅导入此前缀的接口）"
              />
            </Col>
            <Col
              xs={24}
              md={8}
              style={{ display: 'flex', alignItems: 'flex-end' }}
            >
              <Space>
                <Button
                  type="primary"
                  icon={<EyeOutlined />}
                  loading={loading}
                  onClick={handlePreview}
                  size="large"
                >
                  预览解析结果
                </Button>
              </Space>
            </Col>
          </Row>
        )}
      </Card>

      {/* OpenAPI 预览结果 */}
      {(activeTab === 'url' || activeTab === 'json') && loading && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin size="large" description="正在解析 OpenAPI 文档..." />
        </Card>
      )}

      {(activeTab === 'url' || activeTab === 'json') && hasPreviewed && !loading && (
        <Card
          style={{ marginTop: 16 }}
          title={
            <Space>
              <span>解析结果</span>
              <Tag color="blue">{endpoints.length} 个接口</Tag>
              <span style={{ color: '#6b7280', fontWeight: 400 }}>
                已选择 {selectedKeys.length} 个
              </span>
            </Space>
          }
          extra={
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={importing}
              onClick={handleImport}
              size="large"
              disabled={selectedKeys.length === 0}
            >
              导入选中的 {selectedKeys.length} 个接口
            </Button>
          }
        >
          {endpoints.length === 0 ? (
            <Empty description="未解析到任何接口，请检查 URL 或 JSON 内容" />
          ) : (
            <>
              {/* 方法统计 */}
              <Row gutter={16} style={{ marginBottom: 16 }}>
                {Object.entries(methodStats).map(([method, count]) => (
                  <Col xs={12} sm={8} md={6} lg={4} key={method}>
                    <Card size="small">
                      <Statistic
                        title={
                          <Tag color={methodColor[method] || 'default'}>{method}</Tag>
                        }
                        value={count}
                      />
                    </Card>
                  </Col>
                ))}
              </Row>

              <Table
                dataSource={endpoints.map((ep, idx) => ({ ...ep, key: idx }))}
                rowSelection={{
                  selectedRowKeys: selectedKeys,
                  onChange: setSelectedKeys,
                }}
                pagination={{ pageSize: 50, showTotal: (t) => `共 ${t} 条` }}
                columns={[
                  {
                    title: '方法',
                    dataIndex: 'method',
                    width: 70,
                    render: (m: string) => <Tag color={methodColor[m] || 'default'}>{m}</Tag>,
                  },
                  { title: '标题', dataIndex: 'title', ellipsis: true },
                  { title: 'URL', dataIndex: 'url', ellipsis: true },
                  { title: '分组', dataIndex: 'group_path', width: 140,
                    render: (v: string) => <Tag>{v}</Tag> },
                  {
                    title: 'Body',
                    dataIndex: 'body',
                    width: 60,
                    render: (v: any) => (v ? <Tag color="cyan">有</Tag> : '-'),
                  },
                  {
                    title: '断言',
                    dataIndex: 'assertions',
                    width: 60,
                    render: (v: any[]) => v?.length || 0,
                  },
                  {
                    title: '标记',
                    dataIndex: 'markers',
                    width: 120,
                    render: (markers: string[]) =>
                      (markers || []).map((m) => <Tag key={m} color="blue">{m}</Tag>),
                  },
                ]}
              />
            </>
          )}
        </Card>
      )}

      {/* 页面抓取结果 */}
      {activeTab === 'capture' && scanLoading && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin size="large" description="正在扫描页面..." />
        </Card>
      )}

      {activeTab === 'capture' && scanHasResults && !scanLoading && (
        <Card
          style={{ marginTop: 16 }}
          title={
            <Space>
              <span>扫描结果</span>
              <Tag color="blue">{scanEndpoints.length} 个接口</Tag>
              <span style={{ color: '#6b7280', fontWeight: 400 }}>
                已选择 {scanSelectedKeys.length} 个
              </span>
            </Space>
          }
          extra={
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={scanImporting}
              onClick={handleCaptureImport}
              size="large"
              disabled={scanSelectedKeys.length === 0}
            >
              导入选中的 {scanSelectedKeys.length} 个接口
            </Button>
          }
        >
          {scanEndpoints.length === 0 ? (
            <Empty description="未扫描到任何接口，请检查页面 URL" />
          ) : (
            <Table
              dataSource={scanEndpoints.map((ep, idx) => ({ ...ep, key: idx }))}
              rowSelection={{
                selectedRowKeys: scanSelectedKeys,
                onChange: setScanSelectedKeys,
              }}
              pagination={{ pageSize: 50, showTotal: (t) => `共 ${t} 条` }}
              columns={[
                {
                  title: '方法',
                  dataIndex: 'method',
                  width: 80,
                  render: (m: string) => <Tag color={methodColor[m] || 'default'}>{m}</Tag>,
                },
                { title: 'URL', dataIndex: 'url', ellipsis: true },
                { title: '标题', dataIndex: 'title', ellipsis: true },
                {
                  title: '分组',
                  dataIndex: 'group_path',
                  width: 140,
                  render: (v: string) => (v ? <Tag>{v}</Tag> : '-'),
                },
                {
                  title: '来源文件',
                  dataIndex: 'source_file',
                  ellipsis: true,
                  render: (v: string) => v || '-',
                },
              ]}
            />
          )}
        </Card>
      )}

      {/* HAR 抓包预览结果 */}
      {activeTab === 'har' && harLoading && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin size="large" description="正在解析 HAR 文件..." />
        </Card>
      )}

      {activeTab === 'har' && harHasResults && !harLoading && (
        <Card
          style={{ marginTop: 16 }}
          title={
            <Space>
              <span>解析结果</span>
              <Tag color="blue">{harInterfaces.length} 个接口</Tag>
              <span style={{ color: '#6b7280', fontWeight: 400 }}>
                已选择 {harSelectedKeys.length} 个
              </span>
            </Space>
          }
          extra={
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={harImporting}
              onClick={handleHarImport}
              size="large"
              disabled={harSelectedKeys.length === 0}
            >
              导入选中的 {harSelectedKeys.length} 个接口
            </Button>
          }
        >
          {harInterfaces.length === 0 ? (
            <Empty description="未解析到任何接口，请检查 HAR 文件内容" />
          ) : (
            <Table
              dataSource={harInterfaces.map((iface, idx) => ({ ...iface, key: idx }))}
              rowSelection={{
                selectedRowKeys: harSelectedKeys,
                onChange: setHarSelectedKeys,
              }}
              pagination={{ pageSize: 50, showTotal: (t) => `共 ${t} 条` }}
              columns={[
                {
                  title: '方法',
                  dataIndex: 'method',
                  width: 80,
                  render: (m: string) => <Tag color={methodColor[m] || 'default'}>{m}</Tag>,
                },
                { title: '名称', dataIndex: 'suggested_name', width: 160, ellipsis: true },
                { title: '路径', dataIndex: 'path', ellipsis: true },
                { title: '完整 URL', dataIndex: 'full_url', ellipsis: true },
                {
                  title: '状态码',
                  dataIndex: 'response_status',
                  width: 80,
                  render: (v: number) =>
                    v ? <Tag color={v < 400 ? 'green' : 'red'}>{v}</Tag> : '-',
                },
                {
                  title: 'Body',
                  dataIndex: 'body',
                  width: 60,
                  render: (v: any) => (v ? <Tag color="cyan">有</Tag> : '-'),
                },
              ]}
            />
          )}
        </Card>
      )}

      {/* 新建项目 Modal */}
      <Modal
        title="新建项目"
        open={projectModalOpen}
        onOk={handleCreateProject}
        confirmLoading={creatingProject}
        onCancel={() => setProjectModalOpen(false)}
        destroyOnHidden
      >
        <Form form={projectForm} layout="vertical">
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="如：用户中心" />
          </Form.Item>
          <Form.Item name="code" label="项目标识">
            <Input placeholder="如：user-center（可选）" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="如：http://robin.ep.local:30080" />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea rows={3} placeholder="项目描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
