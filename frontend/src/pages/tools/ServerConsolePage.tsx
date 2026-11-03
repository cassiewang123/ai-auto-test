import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Result,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  CloudServerOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import { serverConsoleApi } from '../../services/api';

interface ConnectionForm {
  host: string;
  port: number;
  username: string;
  password: string;
  allowPrivate: boolean;
}

interface KeyValueRow {
  key?: string;
  value?: string;
}

interface RequestForm {
  method: string;
  url: string;
  params: KeyValueRow[];
  headers: KeyValueRow[];
  body: string;
}

interface RunResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  duration: number;
  truncated: boolean;
  command: string;
}

const DEFAULT_CONNECTION: ConnectionForm = {
  host: 'snowflow.cloud',
  port: 22,
  username: 'yhztd',
  password: '',
  allowPrivate: true,
};

const DEFAULT_REQUEST: RequestForm = {
  method: 'POST',
  url: '',
  params: [],
  headers: [{ key: 'Content-Type', value: 'application/json' }],
  body: '',
};

const CONNECTION_STORAGE_KEY = 'airetest.server-console.connection';
const REQUEST_STORAGE_KEY = 'airetest.server-console.request';

function loadSavedConnection(): ConnectionForm {
  try {
    const raw = localStorage.getItem(CONNECTION_STORAGE_KEY);
    if (!raw) return DEFAULT_CONNECTION;
    const parsed = JSON.parse(raw) as Partial<ConnectionForm>;
    return {
      ...DEFAULT_CONNECTION,
      host: parsed.host ?? DEFAULT_CONNECTION.host,
      port: parsed.port ?? DEFAULT_CONNECTION.port,
      username: parsed.username ?? DEFAULT_CONNECTION.username,
      password: '',
      allowPrivate:
        typeof parsed.allowPrivate === 'boolean'
          ? parsed.allowPrivate
          : DEFAULT_CONNECTION.allowPrivate,
    };
  } catch {
    return DEFAULT_CONNECTION;
  }
}

function loadSavedRequest(): RequestForm {
  try {
    const raw = localStorage.getItem(REQUEST_STORAGE_KEY);
    if (!raw) return DEFAULT_REQUEST;
    const parsed = JSON.parse(raw) as Partial<RequestForm>;
    return {
      method: parsed.method === 'GET' ? 'GET' : 'POST',
      url: typeof parsed.url === 'string' ? parsed.url : '',
      params: Array.isArray(parsed.params) ? parsed.params : [],
      headers: Array.isArray(parsed.headers) ? parsed.headers : DEFAULT_REQUEST.headers,
      body: typeof parsed.body === 'string' ? parsed.body : '',
    };
  } catch {
    return DEFAULT_REQUEST;
  }
}

function toRecord(rows: KeyValueRow[] | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  for (const row of rows ?? []) {
    const key = row.key?.trim();
    if (!key) continue;
    result[key] = row.value ?? '';
  }
  return result;
}

function tryPrettyJson(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return text;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return text;
  }
}

function guessFileName(result: RunResult): string {
  const trimmed = result.stdout.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    return `server-response-${Date.now()}.json`;
  }
  return `server-response-${Date.now()}.txt`;
}

export default function ServerConsolePage() {
  const [connectionForm] = Form.useForm<ConnectionForm>();
  const [requestForm] = Form.useForm<RequestForm>();
  const [connection, setConnection] = useState<ConnectionForm>(
    loadSavedConnection
  );
  const [request, setRequest] = useState<RequestForm>(loadSavedRequest);
  const [method, setMethod] = useState<string>(() => loadSavedRequest().method);
  const [viewMode, setViewMode] = useState<'raw' | 'pretty'>('pretty');
  const [testing, setTesting] = useState(false);
  const [running, setRunning] = useState(false);
  const [testBanner, setTestBanner] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    requestForm.setFieldsValue(request);
    // 只在首次挂载时恢复已保存的请求
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const readConnection = (): ConnectionForm => {
    const values = connectionForm.getFieldsValue();
    const next: ConnectionForm = {
      host: values.host?.trim() ?? '',
      port: Number(values.port ?? 22),
      username: values.username?.trim() ?? '',
      password: values.password ?? '',
      allowPrivate: Boolean(values.allowPrivate),
    };
    setConnection(next);
    return next;
  };

  const saveConnection = () => {
    const next = readConnection();
    // 密码仅在本次会话内存中使用，不写入 localStorage
    localStorage.setItem(
      CONNECTION_STORAGE_KEY,
      JSON.stringify({
        host: next.host,
        port: next.port,
        username: next.username,
        allowPrivate: next.allowPrivate,
      })
    );
    message.success('已保存服务器地址和账号，密码不会保存');
  };

  const readRequest = (): RequestForm => {
    const values = requestForm.getFieldsValue();
    const next: RequestForm = {
      method,
      url: values.url?.trim() ?? '',
      params: values.params ?? [],
      headers: values.headers ?? [],
      body: values.body ?? '',
    };
    setRequest(next);
    return next;
  };

  const saveRequest = () => {
    const next = readRequest();
    localStorage.setItem(REQUEST_STORAGE_KEY, JSON.stringify(next));
    message.success('已保存接口和参数');
  };

  const testConnection = async () => {
    const next = readConnection();
    if (!next.host || !next.username || !next.password) {
      message.warning('请先填写服务器地址、账号和密码');
      return;
    }
    setTesting(true);
    setError(null);
    try {
      const response = await serverConsoleApi.test({
        host: next.host,
        port: next.port,
        username: next.username,
        password: next.password,
        allow_private: next.allowPrivate,
        timeout: 20,
      });
      setTestBanner(response.data.server_banner ?? null);
      message.success('SSH 连接成功');
    } catch (exc) {
      setTestBanner(null);
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setTesting(false);
    }
  };

  const execute = async () => {
    const connectionValues = readConnection();
    const requestValues = readRequest();
    if (!connectionValues.host || !connectionValues.username || !connectionValues.password) {
      message.warning('请先填写服务器地址、账号和密码');
      return;
    }
    if (!requestValues.url) {
      message.warning('请输入接口地址');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const response = await serverConsoleApi.request({
        host: connectionValues.host,
        port: connectionValues.port,
        username: connectionValues.username,
        password: connectionValues.password,
        allow_private: connectionValues.allowPrivate,
        method: requestValues.method,
        url: requestValues.url,
        params: toRecord(requestValues.params),
        headers: toRecord(requestValues.headers),
        body:
          requestValues.method === 'GET' || requestValues.method === 'HEAD'
            ? null
            : requestValues.body || null,
        timeout: 120,
      });
      const data = response.data;
      setResult({
        exitCode: data.exit_code,
        stdout: data.stdout,
        stderr: data.stderr,
        duration: data.duration,
        truncated: data.truncated,
        command: data.command,
      });
    } catch (exc) {
      setResult(null);
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setRunning(false);
    }
  };

  const outputText = result
    ? [result.stdout, result.stderr ? `[stderr]\n${result.stderr}` : '']
        .filter(Boolean)
        .join('\n\n')
    : '';
  const displayedOutput =
    viewMode === 'pretty' && result ? tryPrettyJson(result.stdout) : outputText;

  const download = () => {
    if (!result) return;
    const blob = new Blob([outputText], {
      type: 'application/octet-stream;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = guessFileName(result);
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const copyOutput = async () => {
    if (!outputText) return;
    try {
      await navigator.clipboard.writeText(outputText);
      message.success('已复制返回数据');
    } catch {
      message.error('复制失败，请手动选择文本');
    }
  };

  const bodyEnabled = method !== 'GET' && method !== 'HEAD';

  return (
    <ToolPage
      icon={<CloudServerOutlined />}
      title="服务器连接"
      description="通过 SSH 在远程服务器上请求 POST/GET 接口，查看并下载返回数据。"
    >
      <Alert
        type="warning"
        showIcon
        message="安全说明"
        description="密码仅用于本次连接，不写入数据库。请求由后端生成 curl 在服务器上执行，不接受任意 shell 命令。"
      />

      <Row gutter={[16, 16]} align="top">
        <Col xs={24} xl={8}>
          <Card size="small" title="服务器连接" className="server-console-card">
            <Form
              form={connectionForm}
              layout="vertical"
              initialValues={connection}
              onValuesChange={() => setTestBanner(null)}
            >
              <Form.Item
                name="host"
                label="服务器地址"
                rules={[{ required: true, message: '请输入服务器地址' }]}
              >
                <Input prefix={<LinkOutlined />} placeholder="snowflow.cloud" autoComplete="off" />
              </Form.Item>
              <Space.Compact style={{ width: '100%' }}>
                <Form.Item
                  name="port"
                  label="端口"
                  style={{ flex: '0 0 110px', marginBottom: 16 }}
                >
                  <InputNumber min={1} max={65535} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item
                  name="username"
                  label="账号"
                  style={{ flex: 1, marginBottom: 16, marginLeft: 8 }}
                  rules={[{ required: true, message: '请输入账号' }]}
                >
                  <Input placeholder="yhztd" autoComplete="username" />
                </Form.Item>
              </Space.Compact>
              <Form.Item
                name="password"
                label="密码"
                rules={[{ required: true, message: '请输入 SSH 密码' }]}
              >
                <Input.Password placeholder="仅用于本次连接" autoComplete="current-password" />
              </Form.Item>
              <Form.Item
                name="allowPrivate"
                label="允许访问内网地址"
                valuePropName="checked"
                tooltip="开启后可以请求服务器所在内网的 http(s) 地址"
                style={{ marginBottom: 16 }}
              >
                <Switch size="small" />
              </Form.Item>
            </Form>
            <Space wrap>
              <Button icon={<ReloadOutlined />} loading={testing} onClick={testConnection}>
                测试连接
              </Button>
              <Button icon={<SaveOutlined />} onClick={saveConnection}>
                保存地址
              </Button>
            </Space>
            {testBanner ? (
              <div className="server-console-banner">
                <Tag color="green">已连接</Tag>
                <span>{testBanner}</span>
              </div>
            ) : null}
          </Card>
        </Col>

        <Col xs={24} xl={16}>
          <Card
            size="small"
            title="接口请求"
            className="server-console-card"
            extra={
              <Tooltip title="请求会在远程服务器上执行">
                <Tag icon={<CloudServerOutlined />}>远程执行</Tag>
              </Tooltip>
            }
          >
            <Form form={requestForm} layout="vertical" initialValues={request}>
              <Row gutter={12}>
                <Col xs={24} md={5}>
                  <Form.Item label="方法" required>
                    <Select
                      value={method}
                      onChange={(value) => setMethod(value)}
                      options={[
                        { value: 'GET', label: 'GET' },
                        { value: 'POST', label: 'POST' },
                        { value: 'PUT', label: 'PUT' },
                        { value: 'PATCH', label: 'PATCH' },
                        { value: 'DELETE', label: 'DELETE' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={19}>
                  <Form.Item
                    name="url"
                    label="接口地址"
                    rules={[{ required: true, message: '请输入接口地址' }]}
                  >
                    <Input placeholder="https://api.example.com/v1/orders" />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item label="URL 参数（查询字符串）" style={{ marginBottom: 12 }}>
                <Form.List name="params">
                  {(fields, { add, remove }) => (
                    <div className="server-kv-list">
                      {fields.map((field) => (
                        <Space.Compact key={field.key} className="server-kv-row">
                          <Form.Item name={[field.name, 'key']} style={{ marginBottom: 0, flex: 2 }}>
                            <Input placeholder="参数名" />
                          </Form.Item>
                          <Form.Item name={[field.name, 'value']} style={{ marginBottom: 0, flex: 3 }}>
                            <Input placeholder="参数值" />
                          </Form.Item>
                          <Button
                            icon={<DeleteOutlined />}
                            aria-label="删除参数"
                            onClick={() => remove(field.name)}
                          />
                        </Space.Compact>
                      ))}
                      <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>
                        添加参数
                      </Button>
                    </div>
                  )}
                </Form.List>
              </Form.Item>

              <Form.Item label="请求头" style={{ marginBottom: 12 }}>
                <Form.List name="headers">
                  {(fields, { add, remove }) => (
                    <div className="server-kv-list">
                      {fields.map((field) => (
                        <Space.Compact key={field.key} className="server-kv-row">
                          <Form.Item name={[field.name, 'key']} style={{ marginBottom: 0, flex: 2 }}>
                            <Input placeholder="Header 名称" />
                          </Form.Item>
                          <Form.Item name={[field.name, 'value']} style={{ marginBottom: 0, flex: 3 }}>
                            <Input placeholder="Header 值" />
                          </Form.Item>
                          <Button
                            icon={<DeleteOutlined />}
                            aria-label="删除请求头"
                            onClick={() => remove(field.name)}
                          />
                        </Space.Compact>
                      ))}
                      <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>
                        添加请求头
                      </Button>
                    </div>
                  )}
                </Form.List>
              </Form.Item>

              {bodyEnabled ? (
                <Form.Item
                  name="body"
                  label="请求体"
                  tooltip="JSON 请直接在下方粘贴，例如 {&quot;key&quot;:&quot;value&quot;}"
                >
                  <Input.TextArea
                    autoSize={{ minRows: 5, maxRows: 14 }}
                    spellCheck={false}
                    className="server-console-editor"
                    placeholder='{"key":"value"}'
                  />
                </Form.Item>
              ) : null}
            </Form>

            <Space wrap>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={running}
                onClick={execute}
              >
                执行并获取数据
              </Button>
              <Button icon={<SaveOutlined />} onClick={saveRequest}>
                保存参数
              </Button>
              <Button icon={<DownloadOutlined />} disabled={!result} onClick={download}>
                下载返回数据
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

      {error ? (
        <Alert
          type="error"
          showIcon
          closable
          message="执行失败"
          description={error}
          onClose={() => setError(null)}
        />
      ) : null}

      {result ? (
        <Card
          size="small"
          title="返回数据"
          extra={
            <Space>
              <Segmented
                size="small"
                value={viewMode}
                onChange={(value) => setViewMode(value as 'raw' | 'pretty')}
                options={[
                  { label: '格式化', value: 'pretty' },
                  { label: '原始', value: 'raw' },
                ]}
              />
              <Button size="small" icon={<CopyOutlined />} onClick={copyOutput}>
                复制
              </Button>
              <Button size="small" icon={<DownloadOutlined />} onClick={download}>
                下载
              </Button>
            </Space>
          }
        >
          <Descriptions size="small" column={{ xs: 1, sm: 3 }} bordered>
            <Descriptions.Item label="退出码">
              <Tag color={result.exitCode === 0 ? 'green' : 'red'}>
                {result.exitCode ?? '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="耗时">
              <Statistic
                value={result.duration}
                precision={3}
                suffix="s"
                valueStyle={{ fontSize: 14 }}
              />
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {result.truncated ? (
                <Tag color="orange">输出已截断</Tag>
              ) : result.stderr ? (
                <Tag color="orange">有 stderr</Tag>
              ) : (
                <Tag color="green">完成</Tag>
              )}
            </Descriptions.Item>
          </Descriptions>
          {displayedOutput ? (
            <pre className="server-console-output">{displayedOutput}</pre>
          ) : (
            <Result status="success" title="请求完成，无输出" />
          )}
          <details className="server-console-command">
            <summary>查看生成的 curl 命令</summary>
            <pre>{result.command}</pre>
          </details>
        </Card>
      ) : null}
    </ToolPage>
  );
}
