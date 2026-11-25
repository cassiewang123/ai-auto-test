/**
 * 「当前可用变量」查看面板（Popover）。
 *
 * 数据由 useQuickTestVariables 汇聚，本组件只做展示：
 * 三组来源 + 优先级说明 + 被覆盖标记 + 长值/敏感值截断。
 */
import { Popover, Button, Tag, Empty, Spin, Alert, Tooltip } from 'antd';
import { TagsOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  VARIABLE_SOURCE_LABEL,
  type VariableEntry,
  type VariableSource,
} from './useQuickTestVariables';

const SENSITIVE_NAME_PATTERN = /token|secret|pass(word)?|key|authorization|credential|cookie/i;
const MAX_VALUE_LENGTH = 80;

function isSensitiveName(name: string): boolean {
  return SENSITIVE_NAME_PATTERN.test(name);
}

/** 长值截断、敏感值脱敏 */
function displayValue(name: string, value: string): { text: string; tooltip: string | null } {
  if (!value) return { text: '(空)', tooltip: null };
  if (isSensitiveName(name)) {
    return { text: '••••••••（已脱敏）', tooltip: null };
  }
  if (value.length > MAX_VALUE_LENGTH) {
    return { text: `${value.slice(0, MAX_VALUE_LENGTH)}…`, tooltip: value };
  }
  return { text: value, tooltip: null };
}

interface VariableRowProps {
  entry: VariableEntry;
}

function VariableRow({ entry }: VariableRowProps) {
  const { text, tooltip } = displayValue(entry.name, entry.value);
  const valueView = (
    <span
      className="quick-test-variable-value"
      data-testid={`variable-value-${entry.source}-${entry.name}`}
    >
      {text}
    </span>
  );
  return (
    <div className="quick-test-variable-item">
      <div
        className="quick-test-variable-row"
        data-testid={`variable-row-${entry.source}-${entry.name}`}
      >
        <code className="quick-test-variable-name">{entry.name}</code>
        <span className="quick-test-variable-value-cell">
          {tooltip ? (
            <Tooltip title={tooltip} placement="topLeft">
              {valueView}
            </Tooltip>
          ) : (
            valueView
          )}
        </span>
        {entry.overridden ? (
          <Tag className="quick-test-variable-tag" color="orange">
            被覆盖
          </Tag>
        ) : (
          <Tag
            className="quick-test-variable-tag"
            variant="filled"
            data-testid={`variable-source-${entry.source}-${entry.name}`}
          >
            {VARIABLE_SOURCE_LABEL[entry.source]}
          </Tag>
        )}
      </div>
      {/* 环境 base_url 等不可引用项：单独一行醒目说明，不影响上面原有的来源/覆盖标记 */}
      {!entry.referenceable && (
        <div
          className="quick-test-variable-note"
          data-testid={`variable-note-${entry.source}-${entry.name}`}
        >
          <Tag color="orange" className="quick-test-variable-note-tag">
            不可引用
          </Tag>
          {entry.note ?? '仅用于相对 URL 前缀，不可 {{}} 引用'}
        </div>
      )}
    </div>
  );
}

interface VariableGroupProps {
  title: string;
  extra?: React.ReactNode;
  entries: VariableEntry[];
}

function VariableGroup({ title, extra, entries }: VariableGroupProps) {
  return (
    <div className="quick-test-variable-group">
      <div className="quick-test-variable-group-title">
        <span>{title}</span>
        {extra}
      </div>
      {entries.length === 0 ? (
        <div className="quick-test-variable-group-empty">无</div>
      ) : (
        entries.map((entry) => <VariableRow key={`${entry.source}-${entry.name}`} entry={entry} />)
      )}
    </div>
  );
}

export interface VariablesPopoverProps {
  entries: VariableEntry[];
  names: string[];
  loading: boolean;
  error: string | null;
  pageVariablesValid: boolean;
  environmentName?: string;
  onReload: () => void;
}

export default function VariablesPopover({
  entries,
  names,
  loading,
  error,
  pageVariablesValid,
  environmentName,
  onReload,
}: VariablesPopoverProps) {
  const bySource = (source: VariableSource) => entries.filter((entry) => entry.source === source);

  const content = (
    <div className="quick-test-variables-popover" data-testid="variables-panel">
      <div className="quick-test-variables-header">
        <span>
          当前可用变量（{names.length} 个）· 优先级：本页覆盖 &gt; 环境 &gt; 全局
        </span>
        <Button
          size="small"
          type="text"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={onReload}
          aria-label="重新加载变量"
        />
      </div>

      {error && (
        <Alert
          type="warning"
          showIcon
          title="全局变量加载失败"
          description={`${error}（不影响请求执行，可点击右侧按钮重试）`}
          style={{ marginBottom: 8 }}
        />
      )}

      {!error && loading && entries.length === 0 && (
        <div className="quick-test-variables-loading">
          <Spin size="small" /> <span>加载变量中…</span>
        </div>
      )}

      {!error && !loading && entries.length === 0 && (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无可用变量：可在「环境」或「全局变量」页配置"
          style={{ margin: '16px 0' }}
        />
      )}

      {entries.length > 0 && (
        <>
          <VariableGroup
            title="本页覆盖（高级设置 → 环境变量）"
            extra={
              !pageVariablesValid ? (
                <Tag color="red">JSON 无效，本组不会生效</Tag>
              ) : undefined
            }
            entries={bySource('page')}
          />
          <VariableGroup
            title={`环境${environmentName ? ` · ${environmentName}` : ''}（含 base_url）`}
            entries={bySource('environment')}
          />
          <VariableGroup
            title="全局 / 工作区变量"
            extra={error ? <Tag color="orange">加载失败</Tag> : undefined}
            entries={bySource('global')}
          />
        </>
      )}

      <div className="quick-test-variables-footer">
        <div>
          请求中用 <code>{'{{变量名}}'}</code> 引用；同名变量按上面的优先级取值。
        </div>
        <div className="quick-test-variables-footer-note" data-testid="variables-base-url-note">
          <code>base_url</code> 仅用于拼接相对 URL，不作为 <code>{'{{}}'}</code> 变量。
        </div>
      </div>
    </div>
  );

  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      content={content}
      styles={{
        root: { width: 420 },
        content: { padding: 12, maxHeight: 380, overflow: 'auto' },
      }}
    >
      <Button size="small" icon={<TagsOutlined />} data-testid="variables-btn">
        可引用变量{names.length > 0 ? `（${names.length}）` : ''}
      </Button>
    </Popover>
  );
}
