import { useMemo } from 'react';
import { Button, Space, Tag, Tooltip } from 'antd';
import { CompressOutlined, FormatPainterOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import {
  compactJson,
  formatJson,
  type JsonExpectedType,
  validateJsonText,
} from '../utils/json';

const { TextArea } = Input;

interface JsonEditorProps {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  rows?: number;
  expectedType?: JsonExpectedType;
  allowEmpty?: boolean;
  disabled?: boolean;
  autoSize?: boolean | { minRows?: number; maxRows?: number };
  'data-testid'?: string;
}

export default function JsonEditor({
  value = '',
  onChange,
  placeholder,
  rows = 4,
  expectedType = 'any',
  allowEmpty = true,
  disabled = false,
  autoSize,
  'data-testid': testId,
}: JsonEditorProps) {
  const validation = useMemo(
    () => validateJsonText(value, { expectedType, allowEmpty }),
    [allowEmpty, expectedType, value]
  );

  function updateValue(nextValue: string) {
    onChange?.(nextValue);
  }

  function rewrite(style: 'format' | 'compact') {
    if (!validation.valid || validation.value === undefined) return;
    updateValue(
      style === 'format'
        ? formatJson(validation.value)
        : compactJson(validation.value)
    );
  }

  const status = !value.trim()
    ? '未填写'
    : validation.valid
      ? 'JSON 有效'
      : 'JSON 格式错误';

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          marginBottom: 6,
        }}
      >
        <Tag color={!value.trim() ? 'default' : validation.valid ? 'green' : 'red'}>
          {status}
        </Tag>
        <Space size={2}>
          <Tooltip title="格式化 JSON">
            <Button
              type="text"
              size="small"
              icon={<FormatPainterOutlined />}
              disabled={disabled || !validation.valid || validation.value === undefined}
              onClick={() => rewrite('format')}
              aria-label="格式化 JSON"
            />
          </Tooltip>
          <Tooltip title="压缩 JSON">
            <Button
              type="text"
              size="small"
              icon={<CompressOutlined />}
              disabled={disabled || !validation.valid || validation.value === undefined}
              onClick={() => rewrite('compact')}
              aria-label="压缩 JSON"
            />
          </Tooltip>
        </Space>
      </div>
      <TextArea
        rows={rows}
        autoSize={autoSize}
        value={value}
        onChange={(event) => updateValue(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        status={!validation.valid && value.trim() ? 'error' : undefined}
        data-testid={testId}
        style={{ fontFamily: 'Consolas, "Courier New", monospace' }}
      />
      {!validation.valid && value.trim() && (
        <div style={{ color: '#dc2626', fontSize: 12, marginTop: 4 }}>
          {validation.error}
        </div>
      )}
    </div>
  );
}
