import { useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Input,
  Row,
  Space,
  Statistic,
  Table,
  message,
} from 'antd';
import {
  ClearOutlined,
  CopyOutlined,
  FontSizeOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import { countText, wordFrequencies } from '../../utils/tools/textMetrics';

const { TextArea } = Input;

export default function WordCountPage() {
  const [text, setText] = useState('');
  const statistics = useMemo(() => countText(text), [text]);
  const frequencies = useMemo(() => wordFrequencies(text, 20), [text]);

  async function copyStatistics() {
    const report = [
      `字符数：${statistics.characters}`,
      `不含空白字符：${statistics.charactersWithoutSpaces}`,
      `单词数：${statistics.words}`,
      `中文字符：${statistics.chineseCharacters}`,
      `英文字母：${statistics.letters}`,
      `数字：${statistics.digits}`,
      `标点符号：${statistics.punctuation}`,
      `行数：${statistics.lines}`,
      `非空行：${statistics.nonEmptyLines}`,
      `段落数：${statistics.paragraphs}`,
      `UTF-8 字节：${statistics.bytes}`,
    ].join('\n');
    try {
      await navigator.clipboard.writeText(report);
      message.success('统计结果已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  return (
    <ToolPage
      icon={<FontSizeOutlined />}
      title="字数统计"
      description="统计字符、单词、中文字符、段落和文本高频词。"
      extra={
        <Space wrap>
          <Button icon={<ClearOutlined />} onClick={() => setText('')} disabled={!text}>
            清空
          </Button>
          <Button icon={<CopyOutlined />} onClick={copyStatistics} disabled={!text}>
            复制统计
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card size="small" title="文本内容">
          <TextArea
            className="tools-textarea"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={12}
            placeholder="粘贴或输入需要统计的文本"
            data-testid="word-count-input"
          />
        </Card>

        <Card size="small" title="统计结果">
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="字符数" value={statistics.characters} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="单词数" value={statistics.words} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="中文字符" value={statistics.chineseCharacters} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="行数" value={statistics.lines} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="段落数" value={statistics.paragraphs} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="UTF-8 字节" value={statistics.bytes} />
            </Col>
          </Row>
        </Card>

        <Card size="small" title="高频词 Top 20">
          {frequencies.length === 0 ? (
            <div style={{ color: '#9ca3af' }}>输入文本后显示高频词统计。</div>
          ) : (
            <Table
              rowKey="word"
              dataSource={frequencies}
              size="small"
              pagination={false}
              columns={[
                { title: '词', dataIndex: 'word' },
                { title: '出现次数', dataIndex: 'count', width: 140 },
              ]}
            />
          )}
        </Card>
      </div>
    </ToolPage>
  );
}
