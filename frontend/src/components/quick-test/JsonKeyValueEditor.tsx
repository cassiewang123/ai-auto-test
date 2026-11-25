/**
 * 轻量 KV 编辑器：键值表格 + Raw JSON 双模式。
 *
 * 值为字符串形态的 JSON 对象文本（如 `{"a": "b"}`），组件内部维护一份行数据，
 * 外部只通过 onChange 拿到 JSON 文本，因此可直接复用于 Params / Headers / 表单 Body。
 */
import { useEffect, useRef, useState } from 'react';
import { Alert, AutoComplete, Button, Empty, Input, Segmented } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { buildVariableSuggestions } from '../../utils/variableSuggestions';

export interface KeyValueRow {
  id: number;
  key: string;
  value: string;
}

let keyValueRowId = 0;

/** 创建一行带唯一 id 的 KV 数据（用于 React key） */
export function createKeyValueRow(key = '', value = ''): KeyValueRow {
  keyValueRowId += 1;
  return { id: keyValueRowId, key, value };
}

function parseDisplayValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === null || value === undefined) return '';
  return JSON.stringify(value) ?? String(value);
}

function parseInputValue(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return '';
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

/** JSON 文本 → 行数据；非对象或非法 JSON 时返回 valid=false */
export function jsonToRows(value: string): { rows: KeyValueRow[]; valid: boolean } {
  try {
    const parsed = value.trim() ? JSON.parse(value) : {};
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      return { rows: [], valid: false };
    }
    return {
      rows: Object.entries(parsed).map(([key, item]) =>
        createKeyValueRow(key, parseDisplayValue(item))
      ),
      valid: true,
    };
  } catch {
    return { rows: [], valid: false };
  }
}

/** 行数据 → 格式化 JSON 文本 */
export function rowsToJson(
  rows: KeyValueRow[],
  valueMode: 'json' | 'string'
): string {
  const value = rows.reduce<Record<string, unknown>>((result, row) => {
    const key = row.key.trim();
    if (key) {
      result[key] = valueMode === 'string' ? row.value : parseInputValue(row.value);
    }
    return result;
  }, {});
  return JSON.stringify(value, null, 2);
}

export interface JsonKeyValueEditorProps {
  value: string;
  onChange: (value: string) => void;
  keyPlaceholder: string;
  valuePlaceholder: string;
  rawPlaceholder: string;
  valueMode?: 'json' | 'string';
  /** 自定义汇总文案，缺省展示「N 项」 */
  summaryLabel?: string;
  /** 值输入的变量名提示集合（输入 {{ 时弹出候选） */
  variableNames?: string[];
}

/** 值输入框：提供变量名时用 AutoComplete 实现 {{ 候选补全 */
interface ValueInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  variableNames?: string[];
}

function ValueInput({ value, onChange, placeholder, variableNames }: ValueInputProps) {
  if (!variableNames || variableNames.length === 0) {
    return (
      <Input
        value={value}
        placeholder={placeholder}
        aria-label="值"
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  const suggestions = buildVariableSuggestions(value, variableNames);
  return (
    <AutoComplete
      className="quick-test-value-suggest"
      value={value}
      options={suggestions}
      filterOption={false}
      popupMatchSelectWidth={false}
      onChange={(nextValue) => onChange(nextValue ?? '')}
    >
      <Input placeholder={placeholder} aria-label="值" />
    </AutoComplete>
  );
}

export default function JsonKeyValueEditor({
  value,
  onChange,
  keyPlaceholder,
  valuePlaceholder,
  rawPlaceholder,
  valueMode = 'json',
  summaryLabel,
  variableNames,
}: JsonKeyValueEditorProps) {
  const initial = jsonToRows(value);
  const [mode, setMode] = useState<'table' | 'raw'>('table');
  const [rows, setRows] = useState<KeyValueRow[]>(initial.rows);
  const [validJson, setValidJson] = useState(initial.valid);
  const lastEmittedValue = useRef(value);

  useEffect(() => {
    if (value === lastEmittedValue.current) return;
    const parsed = jsonToRows(value);
    setRows(parsed.rows);
    setValidJson(parsed.valid);
    lastEmittedValue.current = value;
  }, [value]);

  function updateRows(nextRows: KeyValueRow[]) {
    const nextValue = rowsToJson(nextRows, valueMode);
    setRows(nextRows);
    setValidJson(true);
    lastEmittedValue.current = nextValue;
    onChange(nextValue);
  }

  function updateRawValue(nextValue: string) {
    onChange(nextValue);
    lastEmittedValue.current = nextValue;
    const parsed = jsonToRows(nextValue);
    setValidJson(parsed.valid);
    if (parsed.valid) setRows(parsed.rows);
  }

  const filledCount = rows.filter((row) => row.key.trim()).length;

  return (
    <div className="quick-test-key-value-editor">
      <div className="quick-test-editor-toolbar">
        <span className="quick-test-editor-summary">
          {validJson
            ? `${filledCount} 项${summaryLabel ? ` · ${summaryLabel}` : ''}`
            : 'JSON 格式错误'}
        </span>
        <Segmented
          size="small"
          value={mode}
          onChange={(nextMode) => setMode(nextMode as 'table' | 'raw')}
          options={[
            { label: '键值', value: 'table' },
            { label: 'Raw JSON', value: 'raw' },
          ]}
        />
      </div>

      {mode === 'raw' ? (
        <Input.TextArea
          rows={8}
          value={value}
          onChange={(event) => updateRawValue(event.target.value)}
          placeholder={rawPlaceholder}
          className="quick-test-raw-editor"
        />
      ) : !validJson ? (
        <Alert
          type="error"
          showIcon
          title="当前内容不是有效的 JSON 对象"
          description="请切换到 Raw JSON 修正格式后，再使用键值视图。"
          action={
            <Button size="small" onClick={() => setMode('raw')}>
              修正 JSON
            </Button>
          }
        />
      ) : (
        <div className="quick-test-key-value-table">
          <div className="quick-test-key-value-head" aria-hidden="true">
            <span>键</span>
            <span>值</span>
            <span />
          </div>
          {rows.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无配置项" />
          ) : (
            rows.map((row) => (
              <div className="quick-test-key-value-row" key={row.id}>
                <Input
                  value={row.key}
                  onChange={(event) =>
                    updateRows(
                      rows.map((item) =>
                        item.id === row.id ? { ...item, key: event.target.value } : item
                      )
                    )
                  }
                  placeholder={keyPlaceholder}
                  aria-label="键"
                />
                <ValueInput
                  value={row.value}
                  onChange={(nextValue) =>
                    updateRows(
                      rows.map((item) =>
                        item.id === row.id ? { ...item, value: nextValue } : item
                      )
                    )
                  }
                  placeholder={valuePlaceholder}
                  variableNames={variableNames}
                />
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => updateRows(rows.filter((item) => item.id !== row.id))}
                  aria-label={`删除 ${row.key || '配置项'}`}
                />
              </div>
            ))
          )}
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            onClick={() => setRows([...rows, createKeyValueRow()])}
          >
            添加一项
          </Button>
        </div>
      )}
    </div>
  );
}
