import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Input, Select, Space, Switch, Tag, message } from 'antd';
import {
  ClearOutlined,
  CodeOutlined,
  CompressOutlined,
  CopyOutlined,
  DownloadOutlined,
  FormatPainterOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import {
  analyzeJson,
  defaultJsonFormatOptions,
  formatJson,
  type JsonFormatOptions,
  type JsonStats,
} from '../../utils/tools/jsonFormatter';

const { TextArea } = Input;

const SAMPLE_JSON = `{"code":200,"message":"成功","data":{"total":236,"page":1,"list":[{"id":"01","name":"服务中心服务申请","enabled":true,"tags":["api","content"]},{"id":"02","name":"服务申请分页查询","enabled":false,"tags":[]}]}}`;

const STORAGE_KEY = 'airetest.tools.json-formatter';

interface StoredState {
  input: string;
  options: JsonFormatOptions;
}

function loadStored(): StoredState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { input: '', options: defaultJsonFormatOptions };
    const parsed = JSON.parse(raw) as Partial<StoredState>;
    return {
      input: typeof parsed.input === 'string' ? parsed.input : '',
      options: { ...defaultJsonFormatOptions, ...(parsed.options ?? {}) },
    };
  } catch {
    return { input: '', options: defaultJsonFormatOptions };
  }
}

const rootTypeLabels: Record<JsonStats['rootType'], string> = {
  object: '对象',
  array: '数组',
  string: '字符串',
  number: '数字',
  boolean: '布尔值',
  null: 'null',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export default function JsonFormatterPage() {
  const stored = useMemo(loadStored, []);
  const [input, setInput] = useState(stored.input);
  const [options, setOptions] = useState<JsonFormatOptions>(stored.options);

  const { output, error, stats } = useMemo(() => {
    if (input.trim() === '') {
      return { output: '', error: null as string | null, stats: null as JsonStats | null };
    }
    try {
      const formatted = formatJson(input, options);
      return { output: formatted, error: null, stats: analyzeJson(input) };
    } catch (formatError) {
      return {
        output: '',
        error: formatError instanceof Error ? formatError.message : '格式化失败',
        stats: null,
      };
    }
  }, [input, options]);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ input, options }));
    } catch {
      // 本地存储不可用时忽略
    }
  }, [input, options]);

  const patchOptions = (patch: Partial<JsonFormatOptions>) =>
    setOptions((prev) => ({ ...prev, ...patch }));

  async function copyOutput() {
    try {
      await navigator.clipboard.writeText(output);
      message.success('已复制格式化结果');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadOutput() {
    const blob = new Blob([output], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = options.indent > 0 ? 'formatted.json' : 'minified.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <ToolPage
      icon={<CodeOutlined />}
      title="JSON 格式化"
      description="美化、压缩、排序与转义 JSON，实时校验语法，全部在浏览器本地完成。"
      extra={
        <Space wrap>
          <Button
            icon={<FormatPainterOutlined />}
            onClick={() => setInput(SAMPLE_JSON)}
            data-testid="json-sample"
          >
            示例
          </Button>
          <Button
            icon={<ClearOutlined />}
            onClick={() => setInput('')}
            disabled={!input}
          >
            清空
          </Button>
          <Button
            type="primary"
            icon={<SwapOutlined />}
            onClick={() => setInput(output)}
            disabled={!output || output === input}
            data-testid="json-apply"
          >
            结果覆盖输入
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card size="small" title="格式化选项">
          <Space wrap size={24}>
            <Space size={8}>
              <span>缩进</span>
              <Select
                size="small"
                style={{ width: 120 }}
                value={options.indent}
                onChange={(indent) => patchOptions({ indent })}
                data-testid="json-indent"
                options={[
                  { value: 2, label: '2 个空格' },
                  { value: 4, label: '4 个空格' },
                  { value: 0, label: '压缩成一行' },
                ]}
              />
            </Space>
            <Space size={8}>
              <span>按 key 排序</span>
              <Switch
                size="small"
                checked={options.sortKeys}
                onChange={(sortKeys) => patchOptions({ sortKeys })}
                data-testid="json-sort-keys"
              />
            </Space>
            <Space size={8}>
              <span>中文转 Unicode 转义</span>
              <Switch
                size="small"
                checked={options.escapeUnicode}
                onChange={(escapeUnicode) => patchOptions({ escapeUnicode })}
                data-testid="json-escape-unicode"
              />
            </Space>
            <Space size={8}>
              <Tag color={options.indent > 0 ? 'blue' : 'orange'}>
                {options.indent > 0 ? <FormatPainterOutlined /> : <CompressOutlined />}
                {' '}
                {options.indent > 0 ? '美化' : '压缩'}
              </Tag>
            </Space>
          </Space>
        </Card>

        {error ? (
          <Alert
            type="error"
            showIcon
            title="JSON 解析失败"
            description={error}
            data-testid="json-error"
          />
        ) : null}

        <div className="tools-two-column">
          <Card size="small" title="输入">
            <TextArea
              className="tools-textarea"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={18}
              placeholder='粘贴 JSON，例如 {"code": 200}'
              data-testid="json-input"
            />
          </Card>
          <Card
            size="small"
            title="格式化结果"
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={copyOutput}
                  disabled={!output}
                  data-testid="json-copy"
                >
                  复制
                </Button>
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={downloadOutput}
                  disabled={!output}
                >
                  导出
                </Button>
              </Space>
            }
          >
            <TextArea
              className="tools-textarea"
              value={output}
              readOnly
              rows={18}
              placeholder="格式化结果会实时显示在这里"
              data-testid="json-output"
            />
            {stats ? (
              <Space wrap size={16} style={{ marginTop: 12, color: '#6b7280', fontSize: 13 }}>
                <span data-testid="json-stats-type">
                  根类型：{rootTypeLabels[stats.rootType]}
                </span>
                <span>字段数：{stats.keys}</span>
                <span>数组元素：{stats.items}</span>
                <span>最大层级：{stats.maxDepth}</span>
                <span>原始大小：{formatBytes(stats.bytes)}</span>
              </Space>
            ) : null}
          </Card>
        </div>
      </div>
    </ToolPage>
  );
}
