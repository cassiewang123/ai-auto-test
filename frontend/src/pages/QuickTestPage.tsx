import { useState, useRef, useEffect } from 'react';
import {
  Card,
  Input,
  Button,
  Select,
  Tabs,
  Space,
  message,
  Tag,
  Spin,
  Table,
  InputNumber,
  Upload,
  Collapse,
  Empty,
  Modal,
  Form,
} from 'antd';
import {
  ThunderboltOutlined,
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  InboxOutlined,
  LinkOutlined,
  KeyOutlined,
  SaveOutlined,
  LockOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import { executionApi, testCaseApi, projectApi, applyAuth, type AuthConfig, type AuthType } from '../services/api';
import type { ExecutionResultData, PreRequest } from '../services/api';
import type { Project } from '../types';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ConsoleWindow, { type ConsoleHandle } from '../components/ConsoleWindow';

const { TextArea } = Input;
const { Dragger } = Upload;

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const ASSERTION_TYPES = ['status_code', 'json_path', 'header', 'response_time', 'json_schema'];
const OPERATORS = ['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'contains', 'regex', 'type'];
const EXTRACT_SOURCES = ['json_path', 'regex', 'header'];

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
};
const statusColor: Record<string, string> = {
  passed: 'green', failed: 'red', error: 'orange',
};

// 文件上传项
interface FileItem {
  file: File;
  field: string;
}

// 前置条件项（带提取规则展开）
interface PreRequestItem extends PreRequest {
  extract_rules: any[];
}

export default function QuickTestPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [method, setMethod] = useState('GET');
  const [url, setUrl] = useState('');
  const [headers, setHeaders] = useState('{\n  "Content-Type": "application/json"\n}');
  const [params, setParams] = useState('{}');
  const [body, setBody] = useState('');
  const [timeout, setTimeoutVal] = useState(30);
  // 重试配置
  const [retryCount] = useState(0);
  const [retryInterval] = useState(0);
  const [assertions, setAssertions] = useState<any[]>([]);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecutionResultData | null>(null);

  // 文件上传
  const [fileItems, setFileItems] = useState<FileItem[]>([]);

  // 前置条件
  const [preRequests, setPreRequests] = useState<PreRequestItem[]>([]);

  // 环境变量
  const [envVariables, setEnvVariables] = useState('{}');

  // 认证配置
  const [authType, setAuthType] = useState<AuthType>('none');
  const [authToken, setAuthToken] = useState('');
  const [apiKeyName, setApiKeyName] = useState('');
  const [apiKeyValue, setApiKeyValue] = useState('');
  const [apiKeyIn, setApiKeyIn] = useState<'header' | 'query'>('header');
  const [basicUser, setBasicUser] = useState('');
  const [basicPass, setBasicPass] = useState('');

  // 前置/后置脚本
  const [preScript, setPreScript] = useState('');
  const [postScript, setPostScript] = useState('');

  // 会话 Cookie
  const [sessionCookies, setSessionCookies] = useState<Array<{ name: string; value: string; path?: string; domain?: string }>>([]);

  // Console 窗口
  const consoleRef = useRef<ConsoleHandle>(null);

  // 保存到接口列表
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [saveForm] = Form.useForm();

  // 从 URL 查询参数预填表单（接口文档"试一下"跳转时携带）
  useEffect(() => {
    const pMethod = searchParams.get('method');
    const pUrl = searchParams.get('url');
    const pHeaders = searchParams.get('headers');
    const pParams = searchParams.get('params');
    const pBody = searchParams.get('body');
    if (pMethod) setMethod(pMethod);
    if (pUrl) setUrl(pUrl);
    if (pHeaders) {
      try { setHeaders(JSON.stringify(JSON.parse(pHeaders), null, 2)); } catch { setHeaders(pHeaders); }
    }
    if (pParams) {
      try { setParams(JSON.stringify(JSON.parse(pParams), null, 2)); } catch { setParams(pParams); }
    }
    if (pBody) {
      try { setBody(JSON.stringify(JSON.parse(pBody), null, 2)); } catch { setBody(pBody); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- 文件处理 ----
  function addFiles(files: FileList | File[] | null) {
    if (!files) return;
    const newItems: FileItem[] = Array.from(files).map((f) => ({
      file: f,
      field: 'file',
    }));
    setFileItems([...fileItems, ...newItems]);
  }

  function removeFile(idx: number) {
    setFileItems(fileItems.filter((_, i) => i !== idx));
  }

  function updateFileField(idx: number, field: string) {
    const next = [...fileItems];
    next[idx] = { ...next[idx], field };
    setFileItems(next);
  }

  // ---- 前置条件 ----
  function addPreRequest() {
    setPreRequests([
      ...preRequests,
      {
        name: `前置请求 ${preRequests.length + 1}`,
        method: 'POST',
        url: '',
        headers: {},
        params: {},
        body: {},
        extract_rules: [],
      },
    ]);
  }

  function updatePreRequest(idx: number, field: keyof PreRequestItem, value: any) {
    const next = [...preRequests];
    next[idx] = { ...next[idx], [field]: value };
    setPreRequests(next);
  }

  function removePreRequest(idx: number) {
    setPreRequests(preRequests.filter((_, i) => i !== idx));
  }

  function addExtractRule(preIdx: number) {
    const next = [...preRequests];
    next[preIdx].extract_rules.push({
      name: '',
      source: 'json_path',
      expression: '',
    });
    setPreRequests(next);
  }

  function updateExtractRule(preIdx: number, ruleIdx: number, field: string, value: any) {
    const next = [...preRequests];
    next[preIdx].extract_rules[ruleIdx] = {
      ...next[preIdx].extract_rules[ruleIdx],
      [field]: value,
    };
    setPreRequests(next);
  }

  function removeExtractRule(preIdx: number, ruleIdx: number) {
    const next = [...preRequests];
    next[preIdx].extract_rules = next[preIdx].extract_rules.filter((_, i) => i !== ruleIdx);
    setPreRequests(next);
  }

  // ---- 断言 ----
  function addAssertion() {
    setAssertions([...assertions, {
      assertion_type: 'status_code', expression: '', operator: 'eq', expected: '200',
    }]);
  }
  function updateAssertion(index: number, field: string, value: any) {
    const next = [...assertions];
    next[index] = { ...next[index], [field]: value };
    setAssertions(next);
  }
  function removeAssertion(index: number) {
    setAssertions(assertions.filter((_, i) => i !== index));
  }

  // ---- 执行 ----
  async function handleExecute() {
    if (!url.trim()) {
      message.warning('请输入请求 URL');
      return;
    }
    let parsedHeaders = {}, parsedParams = {}, parsedBody, parsedVars = {};
    try { parsedHeaders = headers ? JSON.parse(headers) : {}; } catch { message.error('Headers JSON 格式不正确'); return; }
    try { parsedParams = params ? JSON.parse(params) : {}; } catch { message.error('Params JSON 格式不正确'); return; }
    try { if (body.trim()) parsedBody = JSON.parse(body); } catch { message.error('Body JSON 格式不正确'); return; }
    try { parsedVars = envVariables ? JSON.parse(envVariables) : {}; } catch { message.error('环境变量 JSON 格式不正确'); return; }

    // 应用认证配置（合并到 headers / params）
    const authConfig: AuthConfig = {
      type: authType,
      token: authToken || undefined,
      apiKeyName: apiKeyName || undefined,
      apiKeyValue: apiKeyValue || undefined,
      apiKeyIn,
      username: basicUser || undefined,
      password: basicPass || undefined,
    };
    const applied = applyAuth(authConfig, parsedHeaders, parsedParams);
    parsedHeaders = applied.headers;
    parsedParams = applied.params;

    setExecuting(true);
    setResult(null);
    try {
      // 记录前置请求日志
      if (preRequests.length > 0) {
        preRequests.forEach((pre) => {
          consoleRef.current?.log({
            type: 'pre-request',
            method: pre.method,
            url: pre.url,
            message: `${pre.name}: ${pre.method} ${pre.url}`,
          });
        });
      }

      // 记录主请求日志
      consoleRef.current?.log({
        type: 'request',
        method,
        url,
        message: `${method} ${url}`,
      });

      let res;
      if (fileItems.length > 0) {
        res = await executionApi.runMultipart({
          method, url,
          headers: parsedHeaders, params: parsedParams, body: parsedBody,
          assertions, variables: parsedVars, timeout,
          pre_requests: preRequests,
          cookies: sessionCookies,
          pre_script: preScript || undefined,
          post_script: postScript || undefined,
          fileList: fileItems.map((f) => f.file),
          fileFields: fileItems.map((f) => f.field),
        });
      } else {
        res = await executionApi.run({
          method, url,
          headers: parsedHeaders, params: parsedParams, body: parsedBody,
          assertions, variables: parsedVars, timeout,
          pre_requests: preRequests,
          cookies: sessionCookies,
          pre_script: preScript || undefined,
          post_script: postScript || undefined,
        });
      }
      setResult(res.data);

      // 更新会话 Cookie
      if (res.data.session_cookies) {
        setSessionCookies(res.data.session_cookies);
      }

      // 记录响应日志
      if (res.data.response) {
        consoleRef.current?.log({
          type: 'response',
          method,
          url,
          statusCode: res.data.response.status_code,
          status: res.data.status,
          duration: res.data.duration,
          detail: res.data.response.body,
        });
      }

      // 记录断言日志
      if (res.data.assertion_results && res.data.assertion_results.length > 0) {
        res.data.assertion_results.forEach((a) => {
          consoleRef.current?.log({
            type: 'assertion',
            status: a.passed ? 'passed' : 'failed',
            message: `${a.assertion_type}: ${a.expression || ''} ${a.operator} ${a.expected || ''} → ${a.passed ? 'PASS' : 'FAIL'}`,
          });
        });
      }

      if (res.data.error_message) {
        consoleRef.current?.log({
          type: 'error',
          message: res.data.error_message,
        });
      }

      if (res.data.status === 'passed') message.success('测试通过');
      else if (res.data.status === 'failed') message.warning('断言未通过');
      else message.error('执行出错');
    } catch (e: any) {
      consoleRef.current?.log({
        type: 'error',
        message: e.message,
      });
      message.error(e.message);
    } finally {
      setExecuting(false);
    }
  }

  // ---- 保存到接口列表 ----
  useEffect(() => {
    projectApi.listAll().then(res => setProjects(res.data || [])).catch(() => {});
  }, []);

  function openSaveModal() {
    if (!url.trim()) {
      message.warning('请先输入请求 URL');
      return;
    }
    // 自动生成默认标题：METHOD + URL 路径
    let path = url;
    try {
      const u = new URL(url);
      path = u.pathname;
    } catch {
      // Keep the raw URL when it is not absolute.
    }
    const defaultTitle = `${method} ${path}`;
    saveForm.setFieldsValue({
      title: defaultTitle,
      group_path: '',
      project_id: undefined,
    });
    setSaveModalOpen(true);
  }

  async function handleSave() {
    try {
      const values: any = await saveForm.validateFields();
      // 解析当前请求配置
      let parsedHeaders = {}, parsedParams = {}, parsedBody;
      try { parsedHeaders = headers ? JSON.parse(headers) : {}; } catch { message.error('Headers JSON 格式不正确'); return; }
      try { parsedParams = params ? JSON.parse(params) : {}; } catch { message.error('Params JSON 格式不正确'); return; }
      try { if (body.trim()) parsedBody = JSON.parse(body); } catch { message.error('Body JSON 格式不正确'); return; }

      setSaving(true);
      await testCaseApi.create({
        title: values.title,
        method,
        url,
        headers: parsedHeaders,
        params: parsedParams,
        body: parsedBody,
        group_path: values.group_path || undefined,
        project_id: values.project_id || undefined,
        markers: ['quick_test'],
        retry_count: retryCount,
        retry_interval: retryInterval,
        pre_script: preScript || undefined,
        post_script: postScript || undefined,
        auth_type: authType,
        auth_config: authType !== 'none' ? JSON.stringify({
          type: authType,
          token: authToken || undefined,
          apiKeyName: apiKeyName || undefined,
          apiKeyValue: apiKeyValue || undefined,
          apiKeyIn,
          username: basicUser || undefined,
          password: basicPass || undefined,
        }) : undefined,
        session_cookies: sessionCookies.length > 0 ? sessionCookies : undefined,
        assertions: assertions.length > 0 ? assertions.map((a, i) => ({
          assertion_type: a.assertion_type,
          expression: a.expression || null,
          operator: a.operator,
          expected: a.expected,
          priority: 'P1',
          order: i,
        })) : [{
          assertion_type: 'status_code',
          operator: 'eq',
          expected: '200',
          priority: 'P0',
          order: 0,
        }],
      });
      message.success('已保存到接口列表');
      setSaveModalOpen(false);
      // 提示是否跳转
      Modal.confirm({
        title: '保存成功',
        content: '是否立即跳转到接口列表查看？',
        okText: '去查看',
        cancelText: '继续测试',
        onOk: () => navigate('/api-list'),
      });
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <ThunderboltOutlined /><span>快速测试</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              支持 Postman 式文件上传、前置条件、变量提取链
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<SaveOutlined />} onClick={openSaveModal} size="large" data-testid="save-btn">
              保存到接口列表
            </Button>
            <Button type="primary" icon={<SendOutlined />} loading={executing} onClick={handleExecute} size="large" data-testid="send-btn">
              发送请求
            </Button>
          </Space>
        }
      >
        {/* 请求行 */}
        <Space style={{ width: '100%', marginBottom: 16 }} size="middle">
          <Select value={method} onChange={setMethod} style={{ width: 120 }} data-testid="method-select"
            options={METHODS.map((m) => ({ label: m, value: m }))} />
          <Input placeholder="https://api.example.com/users" value={url} data-testid="url-input"
            onChange={(e) => setUrl(e.target.value)} style={{ flex: 1, minWidth: 500 }}
            onPressEnter={handleExecute} />
          <span style={{ color: '#6b7280' }}>超时(s):</span>
          <InputNumber value={timeout} onChange={(v) => setTimeoutVal(v || 30)} min={1} max={300} style={{ width: 80 }} />
        </Space>

        <Tabs
          items={[
            // ---- 请求配置 ----
            {
              key: 'request',
              label: '请求配置',
              children: (
                <>
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Headers (JSON)</label>
                    <TextArea rows={3} value={headers} onChange={(e) => setHeaders(e.target.value)}
                      placeholder='{"Content-Type": "application/json"}' />
                  </div>
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Query Params (JSON)</label>
                    <TextArea rows={3} value={params} onChange={(e) => setParams(e.target.value)}
                      placeholder='{"page": 1, "size": 20}' />
                  </div>
                  <div>
                    <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Body (JSON)</label>
                    <TextArea rows={5} value={body} onChange={(e) => setBody(e.target.value)}
                      placeholder='{"name": "Ada", "email": "ada@example.com"}' />
                  </div>
                </>
              ),
            },
            // ---- 文件上传 ----
            {
              key: 'files',
              label: <span><InboxOutlined /> 文件上传 ({fileItems.length})</span>,
              children: (
                <div>
                  <Dragger
                    beforeUpload={(file) => {
                      addFiles([file]);
                      return false; // 阻止自动上传
                    }}
                    multiple
                    showUploadList={false}
                  >
                    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                    <p className="ant-upload-text">点击或拖拽文件到此处</p>
                    <p className="ant-upload-hint">支持单个或多个文件上传，上传后可设置字段名</p>
                  </Dragger>

                  {fileItems.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                            <th style={{ textAlign: 'left', padding: '8px 12px', width: 150 }}>字段名 (field)</th>
                            <th style={{ textAlign: 'left', padding: '8px 12px' }}>文件名</th>
                            <th style={{ textAlign: 'left', padding: '8px 12px', width: 100 }}>大小</th>
                            <th style={{ width: 60 }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {fileItems.map((item, idx) => (
                            <tr key={idx} style={{ borderBottom: '1px solid #f3f4f6' }}>
                              <td style={{ padding: '8px 12px' }}>
                                <Input size="small" value={item.field}
                                  onChange={(e) => updateFileField(idx, e.target.value)}
                                  placeholder="file" />
                              </td>
                              <td style={{ padding: '8px 12px' }}>{item.file.name}</td>
                              <td style={{ padding: '8px 12px', color: '#6b7280' }}>
                                {(item.file.size / 1024).toFixed(1)} KB
                              </td>
                              <td style={{ textAlign: 'center' }}>
                                <Button type="link" danger size="small" icon={<DeleteOutlined />}
                                  onClick={() => removeFile(idx)} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div style={{ marginTop: 12, padding: 12, background: '#f9fafb', borderRadius: 6, fontSize: 13, color: '#6b7280' }}>
                    提示：上传文件后，主请求将以 multipart/form-data 方式发送。Body 字段将作为表单字段一起提交。
                  </div>
                </div>
              ),
            },
            // ---- 前置条件 ----
            {
              key: 'pre-requests',
              label: <span><LinkOutlined /> 前置条件 ({preRequests.length})</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 12, padding: 12, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    前置条件在主请求之前按顺序执行。从前置请求响应中提取的变量（如 token、id）会自动注入到后续请求中，
                    使用 <code style={{ background: '#dbeafe', padding: '2px 6px', borderRadius: 4 }}>{'{{var_name}}'}</code> 语法引用。
                  </div>

                  {preRequests.length === 0 ? (
                    <Empty description="暂无前置条件" style={{ padding: 20 }} />
                  ) : (
                    <Collapse
                      items={preRequests.map((pre, preIdx) => ({
                        key: String(preIdx),
                        label: (
                          <Space>
                            <Tag color={methodColor[pre.method] || 'default'}>{pre.method}</Tag>
                            <span style={{ fontWeight: 500 }}>{pre.name}</span>
                            <span style={{ color: '#6b7280' }}>{pre.url || '(未设置 URL)'}</span>
                          </Space>
                        ),
                        extra: (
                          <Button type="link" danger size="small" icon={<DeleteOutlined />}
                            onClick={(e) => { e.stopPropagation(); removePreRequest(preIdx); }}>
                            删除
                          </Button>
                        ),
                        children: (
                          <div>
                            <Space style={{ width: '100%', marginBottom: 12 }} size="small">
                              <Input size="small" value={pre.name}
                                onChange={(e) => updatePreRequest(preIdx, 'name', e.target.value)}
                                placeholder="名称" style={{ width: 150 }} />
                              <Select size="small" value={pre.method}
                                onChange={(v) => updatePreRequest(preIdx, 'method', v)}
                                style={{ width: 100 }}
                                options={METHODS.map((m) => ({ label: m, value: m }))} />
                              <Input size="small" value={pre.url}
                                onChange={(e) => updatePreRequest(preIdx, 'url', e.target.value)}
                                placeholder="https://api.example.com/login" style={{ flex: 1, minWidth: 300 }} />
                            </Space>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                              <div>
                                <label style={{ fontSize: 12, color: '#6b7280' }}>Headers (JSON)</label>
                                <TextArea rows={2} size="small"
                                  value={JSON.stringify(pre.headers || {}, null, 0)}
                                  onChange={(e) => {
                                    try { updatePreRequest(preIdx, 'headers', JSON.parse(e.target.value)); } catch {
                                      // Keep the last valid JSON value while editing.
                                    }
                                  }}
                                  placeholder='{"Content-Type": "application/json"}' />
                              </div>
                              <div>
                                <label style={{ fontSize: 12, color: '#6b7280' }}>Body (JSON)</label>
                                <TextArea rows={2} size="small"
                                  value={JSON.stringify(pre.body || {}, null, 0)}
                                  onChange={(e) => {
                                    try { updatePreRequest(preIdx, 'body', JSON.parse(e.target.value)); } catch {
                                      // Keep the last valid JSON value while editing.
                                    }
                                  }}
                                  placeholder='{"username": "admin"}' />
                              </div>
                            </div>

                            {/* 变量提取规则 */}
                            <div style={{ marginTop: 12 }}>
                              <div style={{ marginBottom: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <label style={{ fontSize: 12, color: '#6b7280' }}>
                                  <KeyOutlined /> 变量提取规则
                                </label>
                                <Button size="small" type="dashed" icon={<PlusOutlined />}
                                  onClick={() => addExtractRule(preIdx)}>添加提取</Button>
                              </div>
                              {pre.extract_rules.map((rule, ruleIdx) => (
                                <Space key={ruleIdx} size="small" style={{ display: 'flex', marginBottom: 4 }}>
                                  <Input size="small" value={rule.name}
                                    onChange={(e) => updateExtractRule(preIdx, ruleIdx, 'name', e.target.value)}
                                    placeholder="变量名 (如 token)" style={{ width: 120 }} />
                                  <Select size="small" value={rule.source}
                                    onChange={(v) => updateExtractRule(preIdx, ruleIdx, 'source', v)}
                                    style={{ width: 110 }}
                                    options={EXTRACT_SOURCES.map((s) => ({ label: s, value: s }))} />
                                  <Input size="small" value={rule.expression}
                                    onChange={(e) => updateExtractRule(preIdx, ruleIdx, 'expression', e.target.value)}
                                    placeholder="表达式 (如 $.data.token)" style={{ width: 200 }} />
                                  <Button type="link" danger size="small" icon={<DeleteOutlined />}
                                    onClick={() => removeExtractRule(preIdx, ruleIdx)} />
                                </Space>
                              ))}
                            </div>
                          </div>
                        ),
                      }))}
                    />
                  )}

                  <Button type="dashed" onClick={addPreRequest} block style={{ marginTop: 12 }} icon={<PlusOutlined />}>
                    添加前置请求
                  </Button>
                </div>
              ),
            },
            // ---- 断言规则 ----
            {
              key: 'assertions',
              label: `断言规则 (${assertions.length})`,
              children: (
                <div>
                  {assertions.map((a, idx) => (
                    <Space key={idx} align="baseline" wrap style={{ marginBottom: 8 }}>
                      <Select value={a.assertion_type}
                        onChange={(v) => updateAssertion(idx, 'assertion_type', v)}
                        style={{ width: 140 }}
                        options={ASSERTION_TYPES.map((t) => ({ label: t, value: t }))} />
                      <Input value={a.expression}
                        onChange={(e) => updateAssertion(idx, 'expression', e.target.value)}
                        placeholder="表达式" style={{ width: 180 }} />
                      <Select value={a.operator}
                        onChange={(v) => updateAssertion(idx, 'operator', v)}
                        style={{ width: 110 }}
                        options={OPERATORS.map((o) => ({ label: o, value: o }))} />
                      <Input value={a.expected}
                        onChange={(e) => updateAssertion(idx, 'expected', e.target.value)}
                        placeholder="期望值" style={{ width: 120 }} />
                      <Button type="link" danger onClick={() => removeAssertion(idx)}>删除</Button>
                    </Space>
                  ))}
                  <Button type="dashed" onClick={addAssertion} block>+ 添加断言</Button>
                </div>
              ),
            },
            // ---- 环境变量 ----
            {
              key: 'variables',
              label: <span><KeyOutlined /> 环境变量</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#f0fdf4', borderRadius: 6, fontSize: 13, color: '#166534' }}>
                    环境变量会与前置条件提取的变量合并，用于渲染请求中的 <code>{'{{var}}'}</code> 占位符。
                    前置条件提取的变量优先级高于此处设置的环境变量。
                  </div>
                  <TextArea rows={6} value={envVariables} onChange={(e) => setEnvVariables(e.target.value)}
                    placeholder='{"base_url": "https://api.example.com", "token": "xxx"}' />
                </div>
              ),
            },
            // ---- 认证配置 ----
            {
              key: 'auth',
              label: <span><LockOutlined /> 认证配置</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 12, padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    选择认证类型后自动将认证信息添加到请求头或查询参数。纯前端组装，发送时合并到 headers/params。
                  </div>
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>认证类型</label>
                    <Select
                      value={authType}
                      onChange={setAuthType}
                      style={{ width: 240 }}
                      data-testid="auth-type-select"
                      options={[
                        { label: '无', value: 'none' },
                        { label: 'Bearer Token', value: 'bearer' },
                        { label: 'OAuth2', value: 'oauth2' },
                        { label: 'API Key', value: 'api_key' },
                        { label: 'Basic Auth', value: 'basic' },
                      ]}
                    />
                  </div>

                  {authType === 'bearer' && (
                    <div style={{ marginBottom: 12 }}>
                      <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Token</label>
                      <Input value={authToken} onChange={(e) => setAuthToken(e.target.value)}
                        placeholder="Bearer Token 值" />
                    </div>
                  )}

                  {authType === 'oauth2' && (
                    <div style={{ marginBottom: 12 }}>
                      <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Access Token</label>
                      <Input value={authToken} onChange={(e) => setAuthToken(e.target.value)}
                        placeholder="OAuth2 Access Token" />
                    </div>
                  )}

                  {authType === 'api_key' && (
                    <div style={{ marginBottom: 12 }}>
                      <Space style={{ width: '100%' }} size="middle">
                        <div style={{ flex: 1 }}>
                          <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Key 名</label>
                          <Input value={apiKeyName} onChange={(e) => setApiKeyName(e.target.value)}
                            placeholder="如 X-API-Key" />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Value</label>
                          <Input value={apiKeyValue} onChange={(e) => setApiKeyValue(e.target.value)}
                            placeholder="API Key 值" />
                        </div>
                        <div style={{ width: 140 }}>
                          <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>位置</label>
                          <Select value={apiKeyIn} onChange={setApiKeyIn} style={{ width: '100%' }}
                            options={[{ label: 'Header', value: 'header' }, { label: 'Query', value: 'query' }]} />
                        </div>
                      </Space>
                    </div>
                  )}

                  {authType === 'basic' && (
                    <Space style={{ width: '100%' }} size="middle">
                      <div style={{ flex: 1 }}>
                        <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>用户名</label>
                        <Input value={basicUser} onChange={(e) => setBasicUser(e.target.value)}
                          placeholder="username" />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>密码</label>
                        <Input.Password value={basicPass} onChange={(e) => setBasicPass(e.target.value)}
                          placeholder="password" />
                      </div>
                    </Space>
                  )}

                  {authType === 'none' && (
                    <Empty description="未启用认证" style={{ padding: 20 }} />
                  )}
                </div>
              ),
            },
            // ---- 前后置脚本 ----
            {
              key: 'scripts',
              label: <span><CodeOutlined /> 前后置脚本</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 8, fontWeight: 600 }}>前置脚本 (Python)</div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    主请求执行前运行，可访问 <code>variables</code> 与 <code>request</code>。修改 variables 可影响请求变量渲染。
                  </div>
                  <TextArea rows={5} value={preScript} onChange={(e) => setPreScript(e.target.value)}
                    placeholder={'# 示例\nvariables["trace_id"] = "abc123"\nprint("前置脚本")'}
                    style={{ fontFamily: 'monospace', fontSize: 13, marginBottom: 16 }} data-testid="pre-script-input" />

                  <div style={{ marginBottom: 8, fontWeight: 600 }}>后置脚本 (Python)</div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#f0fdf4', borderRadius: 6, fontSize: 13, color: '#166534' }}>
                    主请求执行后运行，可访问 <code>response</code>（status_code/headers/body/text）与 <code>variables</code>。
                  </div>
                  <TextArea rows={5} value={postScript} onChange={(e) => setPostScript(e.target.value)}
                    placeholder={'# 示例\nif response and response["status_code"] == 200:\n    print("成功")'}
                    style={{ fontFamily: 'monospace', fontSize: 13 }} data-testid="post-script-input" />
                </div>
              ),
            },
            // ---- 会话 Cookie ----
            {
              key: 'cookies',
              label: <span><KeyOutlined /> Cookie ({sessionCookies.length})</span>,
              children: (
                <div data-testid="cookie-panel">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                    <div style={{ padding: 10, background: '#fff7ed', borderRadius: 6, fontSize: 13, color: '#9a3412', flex: 1, marginRight: 12 }}>
                      请求执行后自动捕获响应的 Set-Cookie，下次请求自动带上。Cookie 在当前调试会话内保持。
                    </div>
                    {sessionCookies.length > 0 && (
                      <Button danger icon={<DeleteOutlined />} onClick={() => setSessionCookies([])}>
                        清除全部
                      </Button>
                    )}
                  </div>
                  {sessionCookies.length === 0 ? (
                    <Empty description="暂无会话 Cookie，发送请求后自动捕获" style={{ padding: 20 }} />
                  ) : (
                    <Table
                      dataSource={sessionCookies}
                      rowKey="name"
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '名称', dataIndex: 'name', width: 160,
                          render: (v: string) => <code style={{ fontWeight: 600 }}>{v}</code> },
                        { title: '值', dataIndex: 'value', ellipsis: true,
                          render: (v: string) => <code>{v}</code> },
                        { title: '路径', dataIndex: 'path', width: 100,
                          render: (v: string) => v || '-' },
                        { title: '域名', dataIndex: 'domain', width: 160,
                          render: (v: string) => v || '-' },
                        { title: '', width: 60,
                          render: (_, c) => (
                            <Button type="link" danger size="small" icon={<DeleteOutlined />}
                              onClick={() => setSessionCookies(sessionCookies.filter((x) => x.name !== c.name))} />
                          ) },
                      ]}
                    />
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 前置条件执行结果 */}
      {result && (result as any).pre_request_results && (result as any).pre_request_results.length > 0 && (
        <Card style={{ marginTop: 16 }} title="前置条件执行结果" size="small">
          <Table
            dataSource={(result as any).pre_request_results}
            rowKey="index"
            pagination={false}
            size="small"
            columns={[
              {
                title: '状态', dataIndex: 'success', width: 60,
                render: (s: boolean) => s ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>,
              },
              { title: '名称', dataIndex: 'name', width: 150 },
              { title: '状态码', dataIndex: 'status_code', width: 80,
                render: (v: any) => v || '-' },
              { title: '耗时', dataIndex: 'elapsed', width: 80,
                render: (v: number) => v ? `${v}s` : '-' },
              {
                title: '提取的变量', dataIndex: 'extracted_variables',
                render: (vars: any) => {
                  const entries = Object.entries(vars || {});
                  if (entries.length === 0) return '-';
                  return entries.map(([k, v]) => (
                    <Tag key={k} color="blue">
                      <code>{k}</code> = <code>{String(v).substring(0, 40)}</code>
                    </Tag>
                  ));
                },
              },
              { title: '错误', dataIndex: 'error', render: (v: string) => v ?
                <span style={{ color: '#dc2626' }}>{v}</span> : '-' },
            ]}
          />
        </Card>
      )}

      {/* 主请求执行结果 */}
      {executing && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin size="large" tip="正在发送请求..." />
        </Card>
      )}

      {result && !executing && (
        <Card
          style={{ marginTop: 16 }}
          title={
            <Space>
              <span>执行结果</span>
              <Tag color={statusColor[result.status] || 'default'} style={{ fontSize: 14 }}>{result.status}</Tag>
              <span style={{ color: '#6b7280', fontWeight: 400 }}>耗时 {result.duration.toFixed(3)}s</span>
            </Space>
          }
        >
          {result.error_message ? (
            <pre style={{ background: '#fef2f2', color: '#dc2626', padding: 12, borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap' }}>
              {result.error_message}
            </pre>
          ) : null}

          {result.response && (
            <Card type="inner" title={
              <Space>
                <span>响应</span>
                <Tag color={methodColor[result.response.status_code.toString()] || 'blue'} data-testid="response-status">
                  {result.response.status_code}
                </Tag>
                <span style={{ color: '#6b7280', fontWeight: 400 }}>{result.response.elapsed.toFixed(4)}s</span>
              </Space>
            } style={{ marginBottom: 16 }}>
              <Tabs items={[
                {
                  key: 'body', label: 'Body',
                  children: (
                    <pre style={{ background: '#1a1a2e', color: '#e2e8f0', padding: 16, borderRadius: 8, fontSize: 13, lineHeight: 1.6, maxHeight: 400, overflow: 'auto' }} data-testid="response-body">
                      {typeof result.response.body === 'object'
                        ? JSON.stringify(result.response.body, null, 2)
                        : result.response.text || '(空)'}
                    </pre>
                  ),
                },
                {
                  key: 'headers', label: 'Headers',
                  children: (
                    <pre style={{ background: '#f9fafb', padding: 12, borderRadius: 6, fontSize: 13 }}>
                      {JSON.stringify(result.response.headers, null, 2)}
                    </pre>
                  ),
                },
              ]} />
            </Card>
          )}

          {result.assertion_results && result.assertion_results.length > 0 && (
            <Card type="inner" title="断言结果" style={{ marginBottom: 16 }}>
              <Table
                dataSource={result.assertion_results}
                rowKey={(_, idx) => String(idx)}
                pagination={false} size="small"
                columns={[
                  { title: '结果', dataIndex: 'passed', width: 60,
                    render: (p: boolean) => p ? <Tag color="green">PASS</Tag> : <Tag color="red">FAIL</Tag> },
                  { title: '类型', dataIndex: 'assertion_type', width: 120 },
                  { title: '表达式', dataIndex: 'expression', render: (v: string) => v || '-' },
                  { title: '操作符', dataIndex: 'operator', width: 80 },
                  { title: '期望值', dataIndex: 'expected', width: 80,
                    render: (v: any) => v !== null && v !== undefined ? String(v) : '-' },
                  { title: '实际值', dataIndex: 'actual', width: 80,
                    render: (v: any) => v !== null && v !== undefined ? String(v) : '-' },
                  { title: '说明', dataIndex: 'message', render: (v: string) => v || '-' },
                ]}
              />
            </Card>
          )}

          {result.extracted_variables && result.extracted_variables.length > 0 && (
            <Card type="inner" title="提取的变量">
              <Table
                dataSource={result.extracted_variables}
                rowKey="name" pagination={false} size="small"
                columns={[
                  { title: '变量名', dataIndex: 'name' },
                  { title: '值', dataIndex: 'value',
                    render: (v: any) => (
                      <code style={{ background: '#f3f4f6', padding: '2px 6px', borderRadius: 4 }}>
                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                      </code>
                    ) },
                  { title: '来源', dataIndex: 'source', width: 80 },
                ]}
              />
            </Card>
          )}

          {/* 重试记录 */}
          {result.retry_attempts && result.retry_attempts.length > 1 && (
            <Card type="inner" title="重试记录" style={{ marginBottom: 16 }}>
              <Table
                dataSource={result.retry_attempts}
                rowKey="attempt" pagination={false} size="small"
                columns={[
                  { title: '尝试次数', dataIndex: 'attempt', width: 90 },
                  { title: '状态', dataIndex: 'status', width: 90,
                    render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag> },
                  { title: '状态码', dataIndex: 'status_code', width: 90,
                    render: (c: number) => c || '-' },
                  { title: '耗时(s)', dataIndex: 'duration', width: 90,
                    render: (d: number) => d ? d.toFixed(3) : '-' },
                  { title: '错误', dataIndex: 'error', render: (e: string) => e ?
                    <span style={{ color: '#dc2626' }}>{e}</span> : '-' },
                ]}
              />
            </Card>
          )}

          {/* 脚本执行结果 */}
          {(result.pre_script_result || result.post_script_result) && (
            <Card type="inner" title="脚本执行结果" style={{ marginBottom: 16 }}>
              {result.pre_script_result && (
                <div style={{ marginBottom: 12 }}>
                  <Space>
                    <span style={{ fontWeight: 600 }}>前置脚本：</span>
                    <Tag color={result.pre_script_result.success ? 'green' : 'red'}>
                      {result.pre_script_result.success ? '成功' : '失败'}
                    </Tag>
                  </Space>
                  {result.pre_script_result.output && (
                    <pre style={{ background: '#0f172a', color: '#e2e8f0', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.pre_script_result.output}
                    </pre>
                  )}
                  {result.pre_script_result.error && (
                    <pre style={{ background: '#fef2f2', color: '#dc2626', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.pre_script_result.error}
                    </pre>
                  )}
                </div>
              )}
              {result.post_script_result && (
                <div>
                  <Space>
                    <span style={{ fontWeight: 600 }}>后置脚本：</span>
                    <Tag color={result.post_script_result.success ? 'green' : 'red'}>
                      {result.post_script_result.success ? '成功' : '失败'}
                    </Tag>
                  </Space>
                  {result.post_script_result.output && (
                    <pre style={{ background: '#0f172a', color: '#e2e8f0', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.post_script_result.output}
                    </pre>
                  )}
                  {result.post_script_result.error && (
                    <pre style={{ background: '#fef2f2', color: '#dc2626', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.post_script_result.error}
                    </pre>
                  )}
                </div>
              )}
            </Card>
          )}
        </Card>
      )}

      {/* Console 窗口 */}
      <div style={{ marginTop: 16 }}>
        <ConsoleWindow ref={consoleRef} height={320} />
      </div>

      {/* 保存到接口列表 Modal */}
      <Modal
        title="保存到接口列表"
        open={saveModalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setSaveModalOpen(false)}
        width={520}
        destroyOnClose
      >
        <div style={{ marginBottom: 16, padding: 12, background: '#f9fafb', borderRadius: 6, fontSize: 13 }}>
          <Space>
            <Tag color={methodColor[method] || 'default'} style={{ minWidth: 50, textAlign: 'center' }}>{method}</Tag>
            <span style={{ color: '#6b7280', wordBreak: 'break-all' }}>{url}</span>
          </Space>
        </div>
        <Form form={saveForm} layout="vertical">
          <Form.Item name="title" label="用例标题" rules={[{ required: true, message: '请输入用例标题' }]}>
            <Input placeholder="如：获取用户列表" />
          </Form.Item>
          <Form.Item name="group_path" label="模块/分组">
            <Input placeholder="如：用户管理（可选）" />
          </Form.Item>
          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              options={projects.map(p => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
        </Form>
        <div style={{ color: '#9ca3af', fontSize: 12 }}>
          当前的 Headers、Params、Body、断言规则将一并保存。如果未设置断言，将自动添加 status_code=200 断言。
        </div>
      </Modal>
    </div>
  );
}
