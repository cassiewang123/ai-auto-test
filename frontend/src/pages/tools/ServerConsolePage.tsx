import { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Result,
  Segmented,
  Space,
  Statistic,
  Switch,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  ApiOutlined,
  CloudServerOutlined,
  CopyOutlined,
  DownloadOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons';import ToolPage from '../../components/ToolPage';
import { serverConsoleApi } from '../../services/api';

interface ConnectionForm {
  host: string;
  port: number;
  username: string;
  password: string;
  allowPrivate: boolean;
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

const DEFAULT_COMMAND = `curl -sS -X POST 'https://snowflow.cloud/api/example' \\
  -H 'Content-Type: application/json' \\
  -d '{"key":"value"}'`;

const CONNECTION_STORAGE_KEY = 'airetest.server-console.connection';

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

function formatOutput(result: RunResult | null): string {
  if (!result) return '';
  const parts: string[] = [];
  if (result.stdout) parts.push(result.stdout);
  if (result.stderr) parts.push(`[stderr]\n${result.stderr}`);
  return parts.join('\n\n');
}

function guessFileName(result: RunResult): string {
  const trimmed = result.stdout.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    return `server-response-${Date.now()}.json`;
  }
  return `server-response-${Date.now()}.txt`;
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

export default function ServerConsolePage() {
  const [form] = Form.useForm<ConnectionForm>();
  const [connection, setConnection] = useState<ConnectionForm>(
    loadSavedConnection
  );
  const [command, setCommand] = useState(DEFAULT_COMMAND);
  const [viewMode, setViewMode] = useState<'raw' | 'pretty'>('pretty');
  const [testing, setTesting] = useState(false);
  const [running, setRunning] = useState(false);
  const [testBanner, setTestBanner] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyForm = (): ConnectionForm => {
    const values = form.getFieldsValue();
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
    const next = applyForm();
    // 密码仅在本次会话内存中使用，不写入 localStorage
    const safe = {
      host: next.host,
      port: next.port,
      username: next.username,
      allowPrivate: next.allowPrivate,
    };
    localStorage.setItem(CONNECTION_STORAGE_KEY, JSON.stringify(safe));
    message.success('已保存服务器地址和账号，密码不会保存');
  };

  const testConnection = async () => {
    const next = applyForm();
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
    const next = applyForm();
    if (!next.host || !next.username || !next.password) {
      message.warning('请先填写服务器地址、账号和密码');
      return;
    }
    if (!command.trim()) {
      message.warning('请输入 curl 命令');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const response = await serverConsoleApi.execute({
        host: next.host,
        port: next.port,
        username: next.username,
        password: next.password,
        allow_private: next.allowPrivate,
        command,
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

  const outputText = formatOutput(result);
  const displayedOutput =
    viewMode === 'pretty' && result ? tryPrettyJson(result.stdout) : outputText;

  const download = () => {
    if (!result) return;
    const content =
      result.stderr && result.stdout
        ? `${result.stdout}\n\n[stderr]\n${result.stderr}`
        : result.stdout || result.stderr;
    const blob = new Blob([content], {
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

  return (
    <ToolPage
      icon={<CloudServerOutlined />}
      title="服务器连接"
      description="通过 SSH 登录服务器，执行 curl 命令并下载返回数据。"
    >
      <Alert
        type="warning"
        showIcon
        message="安全说明"
        description="密码仅用于本次连接，不写入数据库。后端只允许执行单条 curl 命令，并拒绝管道、重定向、命令串联和文件协议。"
      />

      <div className="server-console-layout">
        <Card size="small" title="服务器连接" className="server-console-card">
          <Form
            form={form}
            layout="vertical"
            initialValues={connection}
            onValuesChange={() => setTestBanner(null)}
          >
            <Form.Item
              name="host"
              label="服务器地址"
              rules={[{ required: true, message: '请输入服务器地址' }]}
            >
              <Input
                prefix={<LinkOutlined />}
                placeholder="snowflow.cloud"
                autoComplete="off"
              />
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
              <Input.Password
                placeholder="仅用于本次连接"
                autoComplete="current-password"
              />
            </Form.Item>
            <Form.Item
              name="allowPrivate"
              label="允许访问内网地址"
              valuePropName="checked"
              tooltip="开启后 curl 可以访问服务器所在内网的 http(s) 地址"
              style={{ marginBottom: 16 }}
            >
              <Switch size="small" />
            </Form.Item>
          </Form>

          <Space wrap>
            <Button
              icon={<ReloadOutlined />}
              loading={testing}
              onClick={testConnection}
            >
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

        <Card
          size="small"
          title="执行 curl"
          className="server-console-card"
          extra={
            <Tooltip title="只支持单条 curl 命令">
              <Tag icon={<ApiOutlined />}>HTTP</Tag>
            </Tooltip>
          }
        >
          <Input.TextArea
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            autoSize={{ minRows: 7, maxRows: 16 }}
            spellCheck={false}
            className="server-console-editor"
          />
          <div className="server-console-actions">
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={running}
              onClick={execute}
            >
              执行并获取数据
            </Button>
            <Button
              icon={<DownloadOutlined />}
              disabled={!result}
              onClick={download}
            >
              下载返回数据
            </Button>
          </div>
        </Card>
      </div>

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
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={copyOutput}
              >
                复制
              </Button>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={download}
              >
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
            <Result status="success" title="命令执行完成，无输出" />
          )}
        </Card>
      ) : null}
    </ToolPage>
  );
}
