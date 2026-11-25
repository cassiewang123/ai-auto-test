import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Row,
  Space,
  Statistic,
  Tag,
} from 'antd';
import {
  ClearOutlined,
  CopyOutlined,
  DownloadOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import InputOutputPanel from '../../components/tools/InputOutputPanel';
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard';
import { downloadTextFile } from '../../utils/download';
import {
  diffCharsInline,
  diffTextLines,
  type InlineCharDiff,
} from '../../utils/tools/textDiff';

export default function TextComparePage() {
  const [leftText, setLeftText] = useState('');
  const [rightText, setRightText] = useState('');
  // 对比选项：实时生效，只改变比较输入，不改变输出渲染结构
  const [ignoreTrailingWhitespace, setIgnoreTrailingWhitespace] = useState(false);
  const [ignoreBlankLines, setIgnoreBlankLines] = useState(false);
  const [ignoreCase, setIgnoreCase] = useState(false);
  const { copy } = useCopyToClipboard();

  const result = useMemo(
    () =>
      diffTextLines(leftText, rightText, {
        ignoreTrailingWhitespace,
        ignoreBlankLines,
        ignoreCase,
      }),
    [leftText, rightText, ignoreTrailingWhitespace, ignoreBlankLines, ignoreCase]
  );
  const hasInput = leftText !== '' || rightText !== '';

  // 行内字符差异：把「一删一增」的成对修改行做字符级高亮（与 GitHub diff 的行内高亮一致）
  const inlineDiffs = useMemo(() => {
    const map = new Map<number, InlineCharDiff>();
    const lines = result.lines;
    let index = 0;
    while (index < lines.length) {
      if (lines[index].kind === 'same') {
        index += 1;
        continue;
      }
      let blockEnd = index;
      while (blockEnd < lines.length && lines[blockEnd].kind !== 'same') {
        blockEnd += 1;
      }
      const removedIndexes: number[] = [];
      const addedIndexes: number[] = [];
      for (let cursor = index; cursor < blockEnd; cursor += 1) {
        if (lines[cursor].kind === 'removed') removedIndexes.push(cursor);
        else addedIndexes.push(cursor);
      }
      const pairCount = Math.min(removedIndexes.length, addedIndexes.length);
      for (let pair = 0; pair < pairCount; pair += 1) {
        const inline = diffCharsInline(
          lines[removedIndexes[pair]].text,
          lines[addedIndexes[pair]].text,
          { ignoreCase }
        );
        map.set(removedIndexes[pair], inline);
        map.set(addedIndexes[pair], inline);
      }
      index = blockEnd;
    }
    return map;
  }, [result, ignoreCase]);

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

  const copyReport = () =>
    copy(buildReport(), {
      successMessage: '对比结果已复制',
      errorMessage: '复制失败，请检查浏览器剪贴板权限',
    });

  function downloadReport() {
    downloadTextFile(
      `text-compare-${new Date().toISOString().slice(0, 10)}.txt`,
      buildReport(),
      'text/plain;charset=utf-8'
    );
  }

  function renderLineText(lineIndex: number, lineText: string) {
    const inline = inlineDiffs.get(lineIndex);
    if (!inline) return lineText || ' ';
    const side = result.lines[lineIndex].kind === 'removed' ? inline.left : inline.right;
    const joined = side.map((segment) => segment.text).join('');
    if (joined === '') return ' ';
    return side.map((segment, segmentIndex) =>
      segment.changed ? (
        <span key={`changed-${segmentIndex}`} className="tools-diff-char is-changed">
          {segment.text}
        </span>
      ) : (
        <span key={`plain-${segmentIndex}`}>{segment.text}</span>
      )
    );
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
        <InputOutputPanel
          inputTitle="原始文本"
          outputTitle="目标文本"
          inputValue={leftText}
          onInputChange={setLeftText}
          outputValue={rightText}
          onOutputChange={setRightText}
          outputReadOnly={false}
          inputRows={12}
          outputRows={12}
          inputPlaceholder="粘贴原始文本"
          outputPlaceholder="粘贴需要对比的文本"
          inputTestId="text-compare-left"
          outputTestId="text-compare-right"
        />

        <Card size="small" title="对比选项">
          <Space wrap size={24}>
            <Checkbox
              checked={ignoreTrailingWhitespace}
              onChange={(event) => setIgnoreTrailingWhitespace(event.target.checked)}
              data-testid="text-compare-option-trailing"
            >
              忽略行尾空白
            </Checkbox>
            <Checkbox
              checked={ignoreBlankLines}
              onChange={(event) => setIgnoreBlankLines(event.target.checked)}
              data-testid="text-compare-option-blank"
            >
              忽略空行
            </Checkbox>
            <Checkbox
              checked={ignoreCase}
              onChange={(event) => setIgnoreCase(event.target.checked)}
              data-testid="text-compare-option-case"
            >
              忽略大小写
            </Checkbox>
          </Space>
        </Card>

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
                  <span className="tools-diff-text">{renderLineText(index, line.text)}</span>
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
