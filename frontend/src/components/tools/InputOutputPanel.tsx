import type { ReactNode } from 'react';
import { Card, Input } from 'antd';

const { TextArea } = Input;

export interface InputOutputPanelProps {
  /** 左侧输入内容。 */
  inputValue: string;
  onInputChange: (value: string) => void;
  /** 右侧输出内容。 */
  outputValue: string;
  /** 右侧内容变化回调；提供该回调并把 outputReadOnly 设为 false 可让右侧可编辑。 */
  onOutputChange?: (value: string) => void;
  /** 右侧是否只读；默认 true（输入 → 输出类工具）。 */
  outputReadOnly?: boolean;
  inputTitle?: string;
  outputTitle?: string;
  inputPlaceholder?: string;
  outputPlaceholder?: string;
  inputRows?: number;
  outputRows?: number;
  /** 左侧卡片右上角操作区。 */
  inputActions?: ReactNode;
  /** 右侧卡片右上角操作区。 */
  outputActions?: ReactNode;
  /**
   * 自定义输入区节点（如 JsonEditor 等富编辑器）。
   * 提供时将替换默认的 TextArea，忽略 inputValue/onInputChange 相关渲染。
   */
  inputNode?: ReactNode;
  /** 输入框下方自定义区域（如字符统计）。 */
  inputFooter?: ReactNode;
  /** 输出框下方自定义区域（如行数/字符数统计）。 */
  outputFooter?: ReactNode;
  inputTestId?: string;
  outputTestId?: string;
}

/**
 * 工具页通用的「左输入 / 右输出」双列面板。
 *
 * 右侧默认只读，用于展示派生结果；把 `outputReadOnly` 设为 false
 * 并传入 `onOutputChange` 即可复用为「双输入」面板（如文本对比）。
 */
export default function InputOutputPanel({
  inputValue,
  onInputChange,
  outputValue,
  onOutputChange,
  outputReadOnly = true,
  inputTitle = '输入',
  outputTitle = '输出',
  inputPlaceholder,
  outputPlaceholder,
  inputRows = 12,
  outputRows = 12,
  inputActions,
  outputActions,
  inputNode,
  inputFooter,
  outputFooter,
  inputTestId,
  outputTestId,
}: InputOutputPanelProps) {
  return (
    <div className="tools-two-column">
      <Card size="small" title={inputTitle} extra={inputActions}>
        {inputNode ?? (
          <TextArea
            className="tools-textarea"
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            rows={inputRows}
            placeholder={inputPlaceholder}
            data-testid={inputTestId}
          />
        )}
        {inputFooter}
      </Card>
      <Card size="small" title={outputTitle} extra={outputActions}>
        <TextArea
          className="tools-textarea"
          value={outputValue}
          onChange={
            onOutputChange
              ? (event) => onOutputChange(event.target.value)
              : undefined
          }
          readOnly={outputReadOnly}
          rows={outputRows}
          placeholder={outputPlaceholder}
          data-testid={outputTestId}
        />
        {outputFooter}
      </Card>
    </div>
  );
}
