import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Input,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Upload,
  message,
} from 'antd';
import {
  ClearOutlined,
  CopyOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import {
  filterLogs,
  parseLogText,
  summarizeLogs,
  type LogLevel,
} from '../../utils/tools/logAnalysis';

const { TextArea } = Input;

const levelColors: Record<LogLevel, string> = {
  ERROR: 'red',
  WARN: 'orange',
  INFO: 'blue',
  DEBUG: 'default',
  OTHER: 'default',
};

export default function LogAnalysisPage() {
  const [logText, setLogText] = useState('');
  const [selectedLevels, setSelectedLevels] = useState<LogLevel[]>([
    'ERROR',
    'WARN',
    'INFO',
    'DEBUG',
    'OTHER',
  ]);
  const [keyword, setKeyword] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [useRegex, setUseRegex] = useState(false);

  const entries = useMemo(() => parseLogText(logText), [logText]);
  const summary = useMemo(() => summarizeLogs(entries), [entries]);
  const filteredEntries = useMemo(
    () =>
      filterLogs(entries, {
        levels: selectedLevels,
        keyword,
        caseSensitive,
        useRegex,
      }),
    [caseSensitive, entries, keyword, selectedLevels, useRegex]
  );

  async function copyResults() {
    const content = filteredEntries.map((entry) => entry.raw).join('\n');
    try {
      await navigator.clipboard.writeText(content);
      message.success('筛选结果已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadResults() {
    const content = filteredEntries.map((entry) => entry.raw).join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `filtered-logs-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <ToolPage
      icon={<FileSearchOutlined />}
      title="日志分析"
      description="解析日志级别和时间信息，统计错误率并筛选关键日志。"
      extra={
        <Space wrap>
          <Button
            icon={<ClearOutlined />}
            onClick={() => {
              setLogText('');
              setKeyword('');
            }}
            disabled={!logText}
          >
            清空
          </Button>
          <Button
            icon={<CopyOutlined />}
            onClick={copyResults}
            disabled={filteredEntries.length === 0}
          >
            复制结果
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={downloadResults}
            disabled={filteredEntries.length === 0}
          >
            导出结果
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card
          size="small"
          title="日志内容"
          extra={
            <Upload
              accept=".log,.txt,*/*"
              showUploadList={false}
              beforeUpload={(file) => {
                const reader = new FileReader();
                reader.onload = () => setLogText(String(reader.result ?? ''));
                reader.onerror = () => message.error('读取日志文件失败');
                reader.readAsText(file);
                return false;
              }}
            >
              <Button size="small" icon={<UploadOutlined />}>
                导入文件
              </Button>
            </Upload>
          }
        >
          <TextArea
            className="tools-textarea"
            value={logText}
            onChange={(event) => setLogText(event.target.value)}
            rows={10}
            placeholder={'每行一条日志，例如：\n2026-10-08 13:02:00 ERROR request failed'}
            data-testid="log-input"
          />
        </Card>

        <Card size="small" title="统计与过滤">
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <Statistic title="日志总行数" value={summary.total} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic title="错误数" value={summary.byLevel.ERROR} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic title="警告数" value={summary.byLevel.WARN} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title="错误率"
                value={summary.errorRate * 100}
                precision={1}
                suffix="%"
              />
            </Col>
          </Row>
          <Space direction="vertical" size="middle" style={{ width: '100%', marginTop: 16 }}>
            <Checkbox.Group
              className="tools-checkbox-group"
              value={selectedLevels}
              onChange={(values) => setSelectedLevels(values as LogLevel[])}
              options={[
                { value: 'ERROR', label: 'ERROR' },
                { value: 'WARN', label: 'WARN' },
                { value: 'INFO', label: 'INFO' },
                { value: 'DEBUG', label: 'DEBUG' },
                { value: 'OTHER', label: 'OTHER' },
              ]}
            />
            <Space wrap>
              <Input
                style={{ width: 320 }}
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="关键词或正则表达式"
                data-testid="log-keyword"
              />
              <Checkbox
                checked={caseSensitive}
                onChange={(event) => setCaseSensitive(event.target.checked)}
              >
                区分大小写
              </Checkbox>
              <Checkbox
                checked={useRegex}
                onChange={(event) => setUseRegex(event.target.checked)}
              >
                正则搜索
              </Checkbox>
            </Space>
          </Space>
        </Card>

        <Card size="small" title={`筛选结果（${filteredEntries.length} 条）`}>
          {entries.length === 0 ? (
            <Alert type="info" showIcon title="导入或粘贴日志后会自动解析。" />
          ) : filteredEntries.length === 0 ? (
            <Alert type="warning" showIcon title="当前过滤条件下没有匹配日志。" />
          ) : (
            <Table
              rowKey="lineNumber"
              dataSource={filteredEntries}
              size="small"
              pagination={{ pageSize: 20, showSizeChanger: true }}
              scroll={{ x: 860 }}
              columns={[
                { title: '行号', dataIndex: 'lineNumber', width: 80 },
                {
                  title: '级别',
                  dataIndex: 'level',
                  width: 100,
                  render: (level: LogLevel) => <Tag color={levelColors[level]}>{level}</Tag>,
                },
                {
                  title: '时间',
                  dataIndex: 'timestamp',
                  width: 200,
                  render: (value: string | undefined) => value ?? '-',
                },
                { title: '内容', dataIndex: 'message' },
              ]}
            />
          )}
        </Card>
      </div>
    </ToolPage>
  );
}
