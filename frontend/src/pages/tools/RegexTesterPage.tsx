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
  Table,
  Tag,
} from 'antd';
import { ClearOutlined, CodeOutlined, CopyOutlined } from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import InputOutputPanel from '../../components/tools/InputOutputPanel';
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard';
import { buildHighlightSegments, evaluateRegex, replaceRegex } from '../../utils/tools/regexTool';

const flagOptions = [
  { value: 'g', label: '全局匹配 g' },
  { value: 'i', label: '忽略大小写 i' },
  { value: 'm', label: '多行模式 m' },
  { value: 's', label: '点号匹配换行 s' },
];

const samplePattern = '(\\d{4})-(\\d{2})-(\\d{2})';
const sampleText = '开始日期 2026-10-08，结束日期 2026-10-09。';

export default function RegexTesterPage() {
  const [pattern, setPattern] = useState(samplePattern);
  const [flags, setFlags] = useState('g');
  const [text, setText] = useState(sampleText);
  const [replacement, setReplacement] = useState('$1/$2/$3');
  const { copy } = useCopyToClipboard();

  const evaluation = useMemo(
    () => evaluateRegex(pattern, flags, text),
    [pattern, flags, text]
  );

  const replacedText = useMemo(() => {
    if (!evaluation.valid || pattern === '') return text;
    try {
      return replaceRegex(pattern, flags, text, replacement);
    } catch {
      return text;
    }
  }, [evaluation.valid, flags, pattern, replacement, text]);

  // 命中高亮片段：与匹配表格同源（evaluateRegex 的 matches），非法或无匹配时仅展示原文
  const highlightSegments = useMemo(
    () =>
      evaluation.valid && pattern !== '' && text !== ''
        ? buildHighlightSegments(text, evaluation.matches)
        : null,
    [evaluation.valid, evaluation.matches, pattern, text]
  );

  const renderHighlight = () =>
    highlightSegments && (
      <div className="tools-highlight" data-testid="regex-highlight">
        {highlightSegments.map((segment, index) =>
          segment.matched ? (
            <mark key={`match-${index}`}>{segment.text}</mark>
          ) : (
            <span key={`plain-${index}`}>{segment.text}</span>
          )
        )}
      </div>
    );

  const copyReplaced = () =>
    copy(replacedText, {
      successMessage: '替换结果已复制',
      errorMessage: '复制失败，请检查浏览器剪贴板权限',
    });

  return (
    <ToolPage
      icon={<CodeOutlined />}
      title="正则测试"
      description="实时验证表达式，查看匹配内容和捕获分组。"
      extra={
        <Space wrap>
          <Button
            icon={<ClearOutlined />}
            onClick={() => {
              setPattern('');
              setText('');
              setReplacement('');
            }}
          >
            清空
          </Button>
          <Button
            icon={<CopyOutlined />}
            onClick={copyReplaced}
            disabled={pattern === ''}
          >
            复制替换结果
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card size="small" title="表达式">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Input
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              placeholder="输入正则表达式，如 (\\d{4})-(\\d{2})-(\\d{2})"
              data-testid="regex-pattern"
            />
            <Checkbox.Group
              className="tools-checkbox-group"
              value={flags.split('')}
              options={flagOptions}
              onChange={(values) => setFlags(values.join(''))}
            />
          </Space>
        </Card>

        <InputOutputPanel
          inputTitle="测试文本"
          outputTitle="替换为"
          inputValue={text}
          onInputChange={setText}
          outputValue={replacement}
          onOutputChange={setReplacement}
          outputReadOnly={false}
          inputRows={10}
          outputRows={10}
          inputPlaceholder="粘贴需要匹配的文本"
          outputPlaceholder="支持 $1、$2 等分组引用"
          inputTestId="regex-text"
          outputTestId="regex-replacement"
          inputFooter={
            highlightSegments ? (
              <>
                <div className="tools-highlight-title">命中高亮（{evaluation.matches.length} 处）</div>
                {renderHighlight()}
              </>
            ) : null
          }
        />

        {!evaluation.valid ? (
          <Alert type="error" showIcon title="正则表达式无效" description={evaluation.error} />
        ) : (
          <Card
            size="small"
            title={
              <Space>
                <span>匹配结果</span>
                <Tag color={evaluation.matches.length > 0 ? 'green' : 'default'}>
                  {evaluation.matches.length} 处匹配
                </Tag>
              </Space>
            }
          >
            {evaluation.matches.length === 0 ? (
              <Alert type="info" showIcon title="没有匹配结果" />
            ) : (
              <>
                <Table
                  rowKey={(record) => `${record.index}-${record.value}`}
                  dataSource={evaluation.matches}
                  size="small"
                  pagination={{ pageSize: 10, hideOnSinglePage: true }}
                  scroll={{ x: 720 }}
                  columns={[
                    {
                      title: '序号',
                      width: 70,
                      render: (_value, _record, index) => index + 1,
                    },
                    {
                      title: '位置',
                      dataIndex: 'index',
                      width: 90,
                    },
                    {
                      title: '匹配内容',
                      dataIndex: 'value',
                      render: (value: string) => <code>{value}</code>,
                    },
                    {
                      title: '捕获分组',
                      dataIndex: 'groups',
                      render: (groups: string[]) =>
                        groups.length === 0 ? (
                          <span style={{ color: '#9ca3af' }}>-</span>
                        ) : (
                          <Space wrap>
                            {groups.map((group, index) => (
                              <Tag key={`${index}-${group}`}>
                                ${index + 1}: {group || '空'}
                              </Tag>
                            ))}
                          </Space>
                        ),
                    },
                  ]}
                />
                <Row style={{ marginTop: 16 }}>
                  <Col span={24}>
                    <div style={{ marginBottom: 8, color: '#6b7280', fontSize: 13 }}>
                      替换结果
                    </div>
                    <pre className="tools-code-block" data-testid="regex-replaced">
                      {replacedText}
                    </pre>
                  </Col>
                </Row>
              </>
            )}
          </Card>
        )}
      </div>
    </ToolPage>
  );
}
