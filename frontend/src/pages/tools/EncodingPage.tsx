import { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Input,
  Radio,
  Space,
  message,
} from 'antd';
import {
  BgColorsOutlined,
  CopyOutlined,
  DownloadOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import {
  transformText,
  type EncodingDirection,
  type EncodingKind,
} from '../../utils/tools/encodingTool';

const { TextArea } = Input;

const kindOptions: Array<{ value: EncodingKind; label: string }> = [
  { value: 'base64', label: 'Base64' },
  { value: 'url', label: 'URL' },
  { value: 'hex', label: 'Hex' },
  { value: 'unicode', label: 'Unicode' },
  { value: 'html', label: 'HTML 实体' },
];

export default function EncodingPage() {
  const [kind, setKind] = useState<EncodingKind>('base64');
  const [direction, setDirection] = useState<EncodingDirection>('encode');
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [error, setError] = useState<string | null>(null);

  function handleTransform() {
    try {
      setOutput(transformText(input, kind, direction));
      setError(null);
    } catch (transformError) {
      setOutput('');
      setError(
        transformError instanceof Error ? transformError.message : '转换失败，请检查输入内容'
      );
    }
  }

  async function copyOutput() {
    try {
      await navigator.clipboard.writeText(output);
      message.success('转换结果已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadOutput() {
    const blob = new Blob([output], { type: 'text/plain;charset=utf-8' });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `${kind}-${direction}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <ToolPage
      icon={<BgColorsOutlined />}
      title="编码转换"
      description="常用编码与转义格式互转，全部在浏览器本地完成。"
      extra={
        <Space wrap>
          <Button
            icon={<SwapOutlined />}
            onClick={() => {
              setInput(output);
              setOutput(input);
              setDirection(direction === 'encode' ? 'decode' : 'encode');
              setError(null);
            }}
            disabled={!output}
          >
            反向转换
          </Button>
          <Button
            type="primary"
            onClick={handleTransform}
            disabled={input === ''}
            data-testid="encoding-transform"
          >
            {direction === 'encode' ? '编码' : '解码'}
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card size="small" title="转换方式">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Radio.Group
              optionType="button"
              buttonStyle="solid"
              value={kind}
              options={kindOptions}
              onChange={(event) => {
                setKind(event.target.value as EncodingKind);
                setOutput('');
                setError(null);
              }}
            />
            <Radio.Group
              value={direction}
              onChange={(event) => {
                setDirection(event.target.value as EncodingDirection);
                setOutput('');
                setError(null);
              }}
            >
              <Radio.Button value="encode">编码</Radio.Button>
              <Radio.Button value="decode">解码</Radio.Button>
            </Radio.Group>
          </Space>
        </Card>

        {error ? <Alert type="error" showIcon title="转换失败" description={error} /> : null}

        <div className="tools-two-column">
          <Card size="small" title="输入">
            <TextArea
              className="tools-textarea"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={12}
              placeholder="输入需要转换的内容"
              data-testid="encoding-input"
            />
          </Card>
          <Card
            size="small"
            title="输出"
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={copyOutput}
                  disabled={!output}
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
              rows={12}
              placeholder="转换结果显示在这里"
              data-testid="encoding-output"
            />
          </Card>
        </div>
      </div>
    </ToolPage>
  );
}
