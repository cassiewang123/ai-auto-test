/**
 * 请求体编辑器：Body 类型选择 + 各类型独立保留内容。
 *
 * 类型：
 * - none                   不发送 body
 * - json                   沿用 JsonEditor（JSON 文本）
 * - x-www-form-urlencoded   KV 表格，发送时强制 Content-Type
 * - graphql                 query + variables 两段文本
 * - form-data               不自建实现，引导到「高级设置 → 文件上传」
 */
import { Alert, Button, Segmented, Space, Tag } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import JsonEditor from '../JsonEditor';
import JsonKeyValueEditor from './JsonKeyValueEditor';

/** 请求体类型 */
export type BodyType =
  | 'none'
  | 'json'
  | 'x-www-form-urlencoded'
  | 'graphql'
  | 'form-data';

export const BODY_TYPE_OPTIONS: Array<{ label: string; value: BodyType }> = [
  { label: 'none', value: 'none' },
  { label: 'JSON', value: 'json' },
  { label: 'form-urlencoded', value: 'x-www-form-urlencoded' },
  { label: 'GraphQL', value: 'graphql' },
  { label: 'form-data', value: 'form-data' },
];

export interface RequestBodyEditorProps {
  bodyType: BodyType;
  onBodyTypeChange: (bodyType: BodyType) => void;
  jsonBody: string;
  onJsonBodyChange: (value: string) => void;
  formBody: string;
  onFormBodyChange: (value: string) => void;
  graphqlQuery: string;
  onGraphqlQueryChange: (value: string) => void;
  graphqlVariables: string;
  onGraphqlVariablesChange: (value: string) => void;
  /** form-data 类型下展开「高级设置 → 文件上传」 */
  onOpenFileUpload: () => void;
  /** 值输入的变量名提示集合（输入 {{ 时弹出候选） */
  variableNames?: string[];
}

export default function RequestBodyEditor({
  bodyType,
  onBodyTypeChange,
  jsonBody,
  onJsonBodyChange,
  formBody,
  onFormBodyChange,
  graphqlQuery,
  onGraphqlQueryChange,
  graphqlVariables,
  onGraphqlVariablesChange,
  onOpenFileUpload,
  variableNames,
}: RequestBodyEditorProps) {
  return (
    <div className="quick-test-body-editor" data-testid="request-body-editor">
      <div className="quick-test-editor-toolbar">
        <span className="quick-test-editor-summary">请求体类型</span>
        <Segmented
          size="small"
          value={bodyType}
          onChange={(value) => onBodyTypeChange(value as BodyType)}
          options={BODY_TYPE_OPTIONS}
          data-testid="body-type-segmented"
        />
      </div>

      {bodyType === 'none' && (
        <div className="quick-test-body-hint">
          不发送请求体。GET / DELETE 等无 body 的请求保持此选项即可。
        </div>
      )}

      {bodyType === 'json' && (
        <>
          <div className="quick-test-editor-toolbar">
            <span className="quick-test-editor-summary">JSON 请求体</span>
            <Tag variant="filled">application/json</Tag>
          </div>
          <JsonEditor
            value={jsonBody}
            onChange={onJsonBodyChange}
            rows={10}
            placeholder='{"name": "Ada", "email": "ada@example.com"}'
            data-testid="request-body-input"
          />
        </>
      )}

      {bodyType === 'x-www-form-urlencoded' && (
        <>
          <div className="quick-test-body-hint">
            发送时会强制设置 <code>Content-Type: application/x-www-form-urlencoded</code>
            ，值一律按字符串提交。
          </div>
          <JsonKeyValueEditor
            value={formBody}
            onChange={onFormBodyChange}
            keyPlaceholder="字段名"
            valuePlaceholder="字段值"
            rawPlaceholder='{"username": "admin", "password": "123456"}'
            valueMode="string"
            summaryLabel="表单字段"
            variableNames={variableNames}
          />
        </>
      )}

      {bodyType === 'graphql' && (
        <>
          <div className="quick-test-body-hint">
            发送时以 <code>{'{"query": ..., "variables": ...}'}</code> 形式提交，
            变量需填写 JSON 对象（留空视为无变量）。
          </div>
          <div className="quick-test-editor-toolbar">
            <span className="quick-test-editor-summary">Query</span>
            <Tag variant="filled">graphql</Tag>
          </div>
          <JsonEditor
            value={graphqlQuery}
            onChange={onGraphqlQueryChange}
            rows={8}
            allowEmpty
            placeholder={'query User($id: ID!) {\n  user(id: $id) { id name }\n}'}
            data-testid="graphql-query-input"
          />
          <div className="quick-test-editor-toolbar" style={{ marginTop: 12 }}>
            <span className="quick-test-editor-summary">Variables (JSON)</span>
          </div>
          <JsonEditor
            value={graphqlVariables}
            onChange={onGraphqlVariablesChange}
            rows={5}
            expectedType="object"
            placeholder='{"id": "1"}'
            data-testid="graphql-variables-input"
          />
        </>
      )}

      {bodyType === 'form-data' && (
        <Alert
          type="info"
          showIcon
          title="form-data 请使用「高级设置 → 文件上传」"
          description="多文件/表单上传由上传面板统一处理：选择文件后主请求会以 multipart/form-data 发送，文件字段名与 Body 字段都会一并提交。"
          action={
            <Button
              icon={<InboxOutlined />}
              size="small"
              onClick={onOpenFileUpload}
              data-testid="open-file-upload-btn"
            >
              打开文件上传
            </Button>
          }
        />
      )}

      {bodyType === 'form-data' && (
        <Space style={{ marginTop: 8 }} size="small" wrap>
          <Tag color="orange">提示</Tag>
          <span style={{ color: '#64748b', fontSize: 12 }}>
            本页不额外提供表单字段编辑器，避免与上传面板重复维护。
          </span>
        </Space>
      )}
    </div>
  );
}
