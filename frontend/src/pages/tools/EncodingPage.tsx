import { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Radio,
  Space,
  Tooltip,
} from 'antd';
import {
  BgColorsOutlined,
  CopyOutlined,
  DownloadOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import InputOutputPanel from '../../components/tools/InputOutputPanel';
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard';
import { MOD_ENTER_HINT, useModEnter } from '../../hooks/useHotkey';
import { downloadTextFile } from '../../utils/download';
import {
  transformText,
  type EncodingDirection,
  type EncodingKind,
} from '../../utils/tools/encodingTool';

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
  const { copy } = useCopyToClipboard();

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

  // 主操作快捷键：Ctrl/Cmd + Enter 触发编码/解码
  useModEnter(handleTransform, input !== '');

  const copyOutput = () =>
    copy(output, {
      successMessage: '转换结果已复制',
      errorMessage: '复制失败，请检查浏览器剪贴板权限',
    });

  function downloadOutput() {
    downloadTextFile(
      `${kind}-${direction}.txt`,
      output,
      'text/plain;charset=utf-8'
    );
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
          <Tooltip title={`快捷键：${MOD_ENTER_HINT}`}>
            <Button
              type="primary"
              onClick={handleTransform}
              disabled={input === ''}
              data-testid="encoding-transform"
            >
              {direction === 'encode' ? '编码' : '解码'}
            </Button>
          </Tooltip>
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

        <InputOutputPanel
          inputValue={input}
          onInputChange={setInput}
          outputValue={output}
          inputRows={12}
          outputRows={12}
          inputPlaceholder="输入需要转换的内容"
          outputPlaceholder="转换结果显示在这里"
          inputTestId="encoding-input"
          outputTestId="encoding-output"
          outputActions={
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
        />
      </div>
    </ToolPage>
  );
}
