import { useMemo } from 'react';
import { Button, Card, Select, Space, Switch, Tag } from 'antd';
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
import JsonEditor from '../../components/JsonEditor';
import InputOutputPanel from '../../components/tools/InputOutputPanel';
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard';
import { usePersistentState } from '../../hooks/usePersistentState';
import { downloadTextFile } from '../../utils/download';
import {
  analyzeJson,
  defaultJsonFormatOptions,
  formatJson,
  type JsonFormatOptions,
  type JsonStats,
} from '../../utils/tools/jsonFormatter';

const SAMPLE_JSON = `{"code":200,"message":"成功","data":{"total":236,"page":1,"list":[{"id":"01","name":"服务中心服务申请","enabled":true,"tags":["api","content"]},{"id":"02","name":"服务申请分页查询","enabled":false,"tags":[]}]}}`;

const STORAGE_KEY = 'airetest.tools.json-formatter';

const DEFAULT_STORED_STATE: StoredState = {
  input: '',
  options: defaultJsonFormatOptions,
};

interface StoredState {
  input: string;
  options: JsonFormatOptions;
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
  // 输入与选项共用一条历史记录，选项缺省字段由 usePersistentState 自动补齐
  const [stored, setStored] = usePersistentState<StoredState>(
    STORAGE_KEY,
    DEFAULT_STORED_STATE
  );
  const { copy } = useCopyToClipboard();
  const input = stored.input;
  const options = stored.options;

  const setInput = (value: string) =>
    setStored((previous) => ({ ...previous, input: value }));

  const { output, stats } = useMemo(() => {
    if (input.trim() === '') {
      return { output: '', stats: null as JsonStats | null };
    }
    try {
      const formatted = formatJson(input, options);
      return { output: formatted, stats: analyzeJson(input) };
    } catch {
      // 语法错误交由 JsonEditor 内联提示（errorTestId="json-error"），输出区保持为空
      return { output: '', stats: null };
    }
  }, [input, options]);

  const patchOptions = (patch: Partial<JsonFormatOptions>) =>
    setStored((previous) => ({
      ...previous,
      options: { ...previous.options, ...patch },
    }));

  const copyOutput = () =>
    copy(output, {
      successMessage: '已复制格式化结果',
      errorMessage: '复制失败，请检查浏览器剪贴板权限',
    });

  function downloadOutput() {
    downloadTextFile(
      options.indent > 0 ? 'formatted.json' : 'minified.json',
      output,
      'application/json;charset=utf-8'
    );
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

        <InputOutputPanel
          inputNode={
            <JsonEditor
              value={input}
              onChange={setInput}
              rows={18}
              placeholder='粘贴 JSON，例如 {"code": 200}'
              data-testid="json-input"
              errorTestId="json-error"
            />
          }
          inputValue={input}
          onInputChange={setInput}
          outputValue={output}
          inputRows={18}
          outputRows={18}
          inputPlaceholder='粘贴 JSON，例如 {"code": 200}'
          outputPlaceholder="格式化结果会实时显示在这里"
          inputTestId="json-input"
          outputTestId="json-output"
          outputTitle="格式化结果"
          outputActions={
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
          outputFooter={
            stats ? (
              <Space wrap size={16} style={{ marginTop: 12, color: '#6b7280', fontSize: 13 }}>
                <span data-testid="json-stats-type">
                  根类型：{rootTypeLabels[stats.rootType]}
                </span>
                <span>字段数：{stats.keys}</span>
                <span>数组元素：{stats.items}</span>
                <span>最大层级：{stats.maxDepth}</span>
                <span>原始大小：{formatBytes(stats.bytes)}</span>
              </Space>
            ) : null
          }
        />
      </div>
    </ToolPage>
  );
}
