import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Input,
  Row,
  Space,
  Statistic,
  Tag,
  message,
} from 'antd';
import {
  ClearOutlined,
  CopyOutlined,
  DownloadOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import { diffTextLines } from '../../utils/tools/textDiff';

const { TextArea } = Input;

export default function TextComparePage() {
  const [leftText, setLeftText] = useState('');
  const [rightText, setRightText] = useState('');

  const result = useMemo(() => diffTextLines(leftText, rightText), [leftText, rightText]);
  const hasInput = leftText !== '' || rightText !== '';

  function clearAll() {
    setLeftText('');
    setRightText('');
  }

  function swapInputs() {
    setLeftText(rightText);
    setRightText(leftText);
  }

  function buildReport(): string {
    return result.lines
      .map((line) => {
        const marker = line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : ' ';
        return `${marker} ${line.text}`;
      })
      .join('\n');
  }

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(buildReport());
      message.success('对比结果已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadReport() {
    const blob = new Blob([buildReport()], { type: 'text/plain;charset=utf-8' });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `text-compare-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <ToolPage
      icon={<SwapOutlined />}
      title="文本对比"
      description="逐行比较两段文本，输入变化后自动刷新结果。"
      extra={
        <Space wrap>
          <Button icon={<SwapOutlined />} onClick={swapInputs}>
            交换
          </Button>
          <Button icon={<ClearOutlined />} onClick={clearAll}>
            清空
          </Button>
          <Button
            icon={<CopyOutlined />}
            onClick={copyReport}
            disabled={!hasInput}
          >
            复制结果
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={downloadReport}
            disabled={!hasInput}
          >
            导出
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <div className="tools-two-column">
          <Card size="small" title="原始文本">
            <TextArea
              className="tools-textarea"
              value={leftText}
              onChange={(event) => setLeftText(event.target.value)}
              rows={12}
              placeholder="粘贴原始文本"
              data-testid="text-compare-left"
            />
          </Card>
          <Card size="small" title="目标文本">
            <TextArea
              className="tools-textarea"
              value={rightText}
              onChange={(event) => setRightText(event.target.value)}
              rows={12}
              placeholder="粘贴需要对比的文本"
              data-testid="text-compare-right"
            />
          </Card>
        </div>

        <Card size="small" title="对比摘要">
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <Statistic title="新增行" value={result.added} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic title="删除行" value={result.removed} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic title="相同行" value={result.unchanged} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic title="差异总数" value={result.added + result.removed} />
            </Col>
          </Row>
        </Card>

        <Card size="small" title="差异详情">
          {!hasInput ? (
            <Alert type="info" showIcon title="在左右两侧输入或粘贴文本后，这里会显示逐行差异。" />
          ) : result.added + result.removed === 0 ? (
            <Alert type="success" showIcon title="两段文本完全一致" />
          ) : (
            <div className="tools-diff" data-testid="text-diff-result">
              {result.lines.map((line, index) => (
                <div
                  key={`${line.kind}-${index}`}
                  className={`tools-diff-line ${
                    line.kind === 'added'
                      ? 'is-added'
                      : line.kind === 'removed'
                        ? 'is-removed'
                        : ''
                  }`}
                >
                  <span className="tools-diff-number">{line.leftNumber ?? ''}</span>
                  <span className="tools-diff-number">{line.rightNumber ?? ''}</span>
                  <span className="tools-diff-sign">
                    {line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : ' '}
                  </span>
                  <span className="tools-diff-text">{line.text || ' '}</span>
                </div>
              ))}
            </div>
          )}
          <Space style={{ marginTop: 12 }} wrap>
            <Tag color="green">新增</Tag>
            <Tag color="red">删除</Tag>
            <Tag>相同</Tag>
          </Space>
        </Card>
      </div>
    </ToolPage>
  );
}
