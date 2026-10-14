import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Input, Select, Space, Tag, message } from 'antd';
import {
  ClearOutlined,
  CompressOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  FormatPainterOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import {
  compactSql,
  defaultSqlFormatOptions,
  formatSql,
  sqlDialectOptions,
  type SqlFormatOptions,
} from '../../utils/tools/sqlFormatter';

const { TextArea } = Input;

const SAMPLE_SQL = `select u.id,u.name,count(o.id) as order_count from users u left join orders o on o.user_id=u.id where u.status='active' and (o.amount>100 or o.vip=1) group by u.id,u.name having count(o.id)>2 order by order_count desc;`;

const STORAGE_KEY = 'airetest.tools.sql-formatter';

interface StoredState {
  input: string;
  options: SqlFormatOptions;
}

function loadStored(): StoredState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { input: '', options: defaultSqlFormatOptions };
    const parsed = JSON.parse(raw) as Partial<StoredState>;
    return {
      input: typeof parsed.input === 'string' ? parsed.input : '',
      options: { ...defaultSqlFormatOptions, ...(parsed.options ?? {}) },
    };
  } catch {
    return { input: '', options: defaultSqlFormatOptions };
  }
}

function lineCount(text: string): number {
  return text === '' ? 0 : text.split('\n').length;
}

export default function SqlFormatterPage() {
  const stored = useMemo(loadStored, []);
  const [input, setInput] = useState(stored.input);
  const [options, setOptions] = useState<SqlFormatOptions>(stored.options);
  const [output, setOutput] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ input, options }));
    } catch {
      // 本地存储不可用时忽略
    }
  }, [input, options]);

  const patchOptions = (patch: Partial<SqlFormatOptions>) =>
    setOptions((prev) => ({ ...prev, ...patch }));

  function handleFormat() {
    try {
      setOutput(formatSql(input, options));
      setError(null);
    } catch (formatError) {
      setOutput('');
      setError(formatError instanceof Error ? formatError.message : '格式化失败');
    }
  }

  function handleCompact() {
    try {
      setOutput(compactSql(input));
      setError(null);
    } catch (compactError) {
      setOutput('');
      setError(compactError instanceof Error ? compactError.message : '压缩失败');
    }
  }

  async function copyOutput() {
    try {
      await navigator.clipboard.writeText(output);
      message.success('已复制 SQL 结果');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadOutput() {
    const blob = new Blob([output], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'formatted.sql';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const dialect = sqlDialectOptions.find((item) => item.value === options.language);

  return (
    <ToolPage
      icon={<DatabaseOutlined />}
      title="SQL 格式化"
      description="美化或压缩 SQL 语句，支持 Oracle、MySQL、PostgreSQL、Hive 等主流方言，全部在浏览器本地完成。"
      extra={
        <Space wrap>
          <Button
            icon={<FormatPainterOutlined />}
            onClick={() => setInput(SAMPLE_SQL)}
            data-testid="sql-sample"
          >
            示例
          </Button>
          <Button
            icon={<ClearOutlined />}
            onClick={() => {
              setInput('');
              setOutput('');
              setError(null);
            }}
            disabled={!input}
          >
            清空
          </Button>
          <Button
            icon={<CompressOutlined />}
            onClick={handleCompact}
            disabled={input.trim() === ''}
            data-testid="sql-compact"
          >
            压缩
          </Button>
          <Button
            type="primary"
            icon={<SwapOutlined />}
            onClick={handleFormat}
            disabled={input.trim() === ''}
            data-testid="sql-format"
          >
            格式化
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card size="small" title="格式化选项">
          <Space wrap size={24}>
            <Space size={8}>
              <span>方言</span>
              <Select
                size="small"
                style={{ width: 190 }}
                value={options.language}
                onChange={(language) => patchOptions({ language })}
                data-testid="sql-dialect"
                options={sqlDialectOptions.map(({ value, label, description }) => ({
                  value,
                  label,
                  title: description,
                }))}
              />
            </Space>
            <Space size={8}>
              <span>关键字大小写</span>
              <Select
                size="small"
                style={{ width: 120 }}
                value={options.keywordCase}
                onChange={(keywordCase) => patchOptions({ keywordCase })}
                data-testid="sql-keyword-case"
                options={[
                  { value: 'upper', label: '大写' },
                  { value: 'lower', label: '小写' },
                  { value: 'preserve', label: '保持原样' },
                ]}
              />
            </Space>
            <Space size={8}>
              <span>缩进</span>
              <Select
                size="small"
                style={{ width: 110 }}
                value={options.indent}
                onChange={(indent) => patchOptions({ indent })}
                options={[
                  { value: 2, label: '2 个空格' },
                  { value: 4, label: '4 个空格' },
                ]}
              />
            </Space>
            <Space size={8}>
              <span>AND/OR 换行</span>
              <Select
                size="small"
                style={{ width: 110 }}
                value={options.logicalOperatorNewline}
                onChange={(logicalOperatorNewline) =>
                  patchOptions({ logicalOperatorNewline })
                }
                options={[
                  { value: 'before', label: '换行前' },
                  { value: 'after', label: '换行后' },
                ]}
              />
            </Space>
            <Space size={8}>
              <span>最大行宽</span>
              <Select
                size="small"
                style={{ width: 100 }}
                value={options.expressionWidth}
                onChange={(expressionWidth) => patchOptions({ expressionWidth })}
                options={[
                  { value: 60, label: '60' },
                  { value: 80, label: '80' },
                  { value: 120, label: '120' },
                ]}
              />
            </Space>
            {dialect ? <Tag color="blue">{dialect.description}</Tag> : null}
          </Space>
        </Card>

        {error ? (
          <Alert
            type="error"
            showIcon
            title="SQL 处理失败"
            description={error}
            data-testid="sql-error"
          />
        ) : null}

        <div className="tools-two-column">
          <Card size="small" title="输入">
            <TextArea
              className="tools-textarea"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={20}
              placeholder="粘贴需要格式化的 SQL 语句"
              data-testid="sql-input"
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
                  data-testid="sql-copy"
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
              rows={20}
              placeholder="点击“格式化”后结果显示在这里"
              data-testid="sql-output"
            />
            {output ? (
              <Space wrap size={16} style={{ marginTop: 12, color: '#6b7280', fontSize: 13 }}>
                <span>{lineCount(output)} 行</span>
                <span>{output.length} 字符</span>
              </Space>
            ) : null}
          </Card>
        </div>
      </div>
    </ToolPage>
  );
}
