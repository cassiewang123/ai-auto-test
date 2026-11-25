import { useState, useRef, useEffect } from 'react';
import {
  Card,
  Input,
  Button,
  Select,
  Tabs,
  Space,
  message,
  Tag,
  Spin,
  Table,
  InputNumber,
  Upload,
  Collapse,
  Empty,
  Modal,
  Form,
  Divider,
  Tooltip,
  AutoComplete,
} from 'antd';
import {
  ThunderboltOutlined,
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  InboxOutlined,
  LinkOutlined,
  KeyOutlined,
  SaveOutlined,
  LockOutlined,
  CodeOutlined,
  CopyOutlined,
  ImportOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { executionApi, testCaseApi, projectApi, applyAuth, type AuthConfig, type AuthType } from '../services/api';
import type { CallHistoryRecord, ExecutionResultData, PreRequest } from '../services/api';
import type { Project } from '../types';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ConsoleWindow, { type ConsoleHandle } from '../components/ConsoleWindow';
import JsonKeyValueEditor from '../components/quick-test/JsonKeyValueEditor';
import HistoryPanel from '../components/quick-test/HistoryPanel';
import CurlImportModal from '../components/quick-test/CurlImportModal';
import RequestBodyEditor, { type BodyType } from '../components/quick-test/RequestBodyEditor';
import ResponseViewer from '../components/quick-test/ResponseViewer';
import VariablesPopover from '../components/quick-test/VariablesPopover';
import { useQuickTestVariables } from '../components/quick-test/useQuickTestVariables';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { parseJsonText } from '../utils/json';
import { toCurl, parseUrlEncodedBody } from '../utils/tools/curl';
import { copyTextToClipboard } from '../utils/clipboard';
import { buildVariableSuggestions } from '../utils/variableSuggestions';
import '../styles/quick-test-workspace.css';

const { TextArea } = Input;
const { Dragger } = Upload;

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const ASSERTION_TYPES = ['status_code', 'json_path', 'header', 'response_time', 'json_schema'];
const OPERATORS = ['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'contains', 'regex', 'type'];
const EXTRACT_SOURCES = ['json_path', 'regex', 'header'];

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'orange', PUT: 'blue', PATCH: 'purple', DELETE: 'red',
};
const statusColor: Record<string, string> = {
  passed: 'green', failed: 'red', error: 'orange',
};

/** 断言模板：一键插入一条常用断言（插入后仍可编辑，不覆盖已有行） */
interface AssertionTemplate {
  key: string;
  label: string;
  hint: string;
  assertion: {
    assertion_type: string;
    expression?: string;
    operator?: string;
    expected?: string;
  };
}

const ASSERTION_TEMPLATES: AssertionTemplate[] = [
  {
    key: 'status-200',
    label: '状态码 = 200',
    hint: '校验 HTTP 状态码等于 200',
    assertion: { assertion_type: 'status_code', operator: 'eq', expected: '200' },
  },
  {
    key: 'response-time',
    label: '响应时间 < 1000ms',
    hint: '校验响应耗时小于 1000 毫秒',
    assertion: { assertion_type: 'response_time', operator: 'lt', expected: '1000' },
  },
  {
    key: 'body-contains',
    label: '响应包含指定文本',
    hint: '在响应体根节点搜索文本，期望值待填写',
    assertion: { assertion_type: 'json_path', expression: '$.', operator: 'contains', expected: '' },
  },
  {
    key: 'biz-code',
    label: '业务码 $.code = 0',
    hint: '校验响应 JSON 的 code 字段等于 0',
    assertion: { assertion_type: 'json_path', expression: '$.code', operator: 'eq', expected: '0' },
  },
  {
    key: 'header-exists',
    label: '响应头存在',
    hint: '校验指定响应头（如 Content-Type）包含某文本，期望值待填写',
    assertion: { assertion_type: 'header', expression: 'Content-Type', operator: 'contains', expected: '' },
  },
  {
    key: 'json-schema',
    label: 'JSON Schema 校验',
    hint: '用 JSON Schema 校验响应体结构（预填对象骨架，operator 不参与校验）',
    assertion: {
      assertion_type: 'json_schema',
      operator: 'eq',
      expected: '{\n  "type": "object"\n}',
    },
  },
];

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  const parsed = value.trim() ? JSON.parse(value) : {};
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(`${label} 必须是 JSON 对象`);
  }
  return parsed as Record<string, unknown>;
}

function parseHeadersJson(value: string): Record<string, string> {
  const parsed = parseJsonObject(value, 'Headers');
  return Object.fromEntries(
    Object.entries(parsed).map(([key, item]) => [
      key,
      item === null || item === undefined
        ? ''
        : typeof item === 'string'
          ? item
          : JSON.stringify(item),
    ])
  );
}

/** 大小写不敏感地判断是否已存在某个 header */
function hasHeader(headers: Record<string, string>, name: string): boolean {
  const target = name.toLowerCase();
  return Object.keys(headers).some((key) => key.toLowerCase() === target);
}

/** 解析后的请求配置（执行与保存共用，保证两条链路 payload 一致） */
interface ParsedRequestParts {
  headers: Record<string, string>;
  params: Record<string, unknown>;
  body: unknown;
  graphqlQuery?: string;
}

// 文件上传项
interface FileItem {
  file: File;
  field: string;
}

// 前置条件项（带提取规则展开）
interface PreRequestItem extends PreRequest {
  extract_rules: any[];
}

export default function QuickTestPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const {
    environments,
    selectedProjectId,
    selectedEnvironmentId,
    setSelectedEnvironmentId,
    setSelectedProjectId,
  } = useWorkspace();
  const sourceCaseId = searchParams.get('case_id');
  const selectedEnvironment = environments.find(
    (environment) => environment.id === selectedEnvironmentId,
  );
  // 环境被删除后清理本地缓存的选择，避免执行时携带失效 ID
  useEffect(() => {
    if (
      selectedEnvironmentId &&
      environments.length > 0 &&
      !selectedEnvironment
    ) {
      setSelectedEnvironmentId(null);
    }
  }, [
    environments,
    selectedEnvironment,
    selectedEnvironmentId,
    setSelectedEnvironmentId,
  ]);
  const workspaceVariables = {
    ...(selectedEnvironment?.base_url ? { base_url: selectedEnvironment.base_url } : {}),
    ...(selectedEnvironment?.variables || {}),
  };
  const [method, setMethod] = useState('GET');
  const [url, setUrl] = useState('');
  const [headers, setHeaders] = useState('{\n  "Content-Type": "application/json"\n}');
  const [params, setParams] = useState('{}');
  const [body, setBody] = useState('');
  // Body 类型与各类型的独立编辑内容（切换类型不清空）
  const [bodyType, setBodyType] = useState<BodyType>('json');
  const [formBody, setFormBody] = useState('{}');
  const [graphqlQuery, setGraphqlQuery] = useState('');
  const [graphqlVariables, setGraphqlVariables] = useState('{}');
  const [timeout, setTimeoutVal] = useState(30);
  // 重试配置
  const [retryCount, setRetryCount] = useState(0);
  const [retryInterval, setRetryInterval] = useState(0);
  const [assertions, setAssertions] = useState<any[]>([]);
  const [extractRules, setExtractRules] = useState<any[]>([]);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecutionResultData | null>(null);

  // 文件上传
  const [fileItems, setFileItems] = useState<FileItem[]>([]);

  // 前置条件
  const [preRequests, setPreRequests] = useState<PreRequestItem[]>([]);

  // 环境变量
  const [envVariables, setEnvVariables] = useState('{}');

  // 认证配置
  const [authType, setAuthType] = useState<AuthType>('none');
  const [authToken, setAuthToken] = useState('');
  const [apiKeyName, setApiKeyName] = useState('');
  const [apiKeyValue, setApiKeyValue] = useState('');
  const [apiKeyIn, setApiKeyIn] = useState<'header' | 'query'>('header');
  const [basicUser, setBasicUser] = useState('');
  const [basicPass, setBasicPass] = useState('');

  // 前置/后置脚本
  const [preScript, setPreScript] = useState('');
  const [postScript, setPostScript] = useState('');

  // 会话 Cookie
  const [sessionCookies, setSessionCookies] = useState<Array<{ name: string; value: string; path?: string; domain?: string }>>([]);

  // Console 窗口
  const consoleRef = useRef<ConsoleHandle>(null);

  // 保存到接口列表 / 更新用例
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sourceCaseLoading, setSourceCaseLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [saveForm] = Form.useForm();
  // 由 case_id 载入的用例 id：保存时走 update 而不是 create
  const [loadedCaseId, setLoadedCaseId] = useState<string | null>(null);

  // 页内历史面板
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  // cURL 导入弹窗
  const [curlModalOpen, setCurlModalOpen] = useState(false);

  // 高级设置（Collapse 与内层 Tabs 受控，便于从 form-data 一键展开文件上传）
  const [advancedKeys, setAdvancedKeys] = useState<string[]>([]);
  const [advancedTabKey, setAdvancedTabKey] = useState('files');

  // 取消请求
  const abortRef = useRef<AbortController | null>(null);

  // A9：当前请求实际可用的全部变量（全局 → 环境 → 本页覆盖，与后端合并顺序一致）
  const quickTestVariables = useQuickTestVariables({
    environment: selectedEnvironment
      ? {
          id: selectedEnvironment.id,
          name: selectedEnvironment.name,
          base_url: selectedEnvironment.base_url,
          variables: selectedEnvironment.variables,
        }
      : null,
    pageVariablesText: envVariables,
    projectId: selectedProjectId,
  });
  const variableNames = quickTestVariables.names;
  const urlSuggestions = buildVariableSuggestions(url, variableNames);

  // 已保存用例仅通过 case_id 交接，避免请求头和认证信息进入浏览器历史。
  useEffect(() => {
    if (sourceCaseId) {
      let active = true;
      setSourceCaseLoading(true);
      testCaseApi
        .get(sourceCaseId)
        .then((response) => {
          if (!active) return;
          const testCase = response.data;
          setLoadedCaseId(testCase.id ?? sourceCaseId);
          setMethod(testCase.method);
          setUrl(testCase.url);
          setHeaders(JSON.stringify(testCase.headers || {}, null, 2));
          setParams(JSON.stringify(testCase.params || {}, null, 2));
          setBody(
            testCase.body === null || testCase.body === undefined
              ? ''
              : JSON.stringify(testCase.body, null, 2)
          );
          // GraphQL 用例：query 走 graphql_query，body 即 variables
          setGraphqlQuery(testCase.graphql_query || '');
          setGraphqlVariables(
            testCase.graphql_query && testCase.body
              ? JSON.stringify(testCase.body, null, 2)
              : '{}'
          );
          setBodyType(testCase.graphql_query ? 'graphql' : 'json');
          setAssertions(
            (testCase.assertions || []).map((assertion) => ({
              assertion_type: assertion.assertion_type,
              expression: assertion.expression || '',
              operator: assertion.operator,
              expected: assertion.expected ?? '',
            }))
          );
          setExtractRules(testCase.extract_rules || []);
          setRetryCount(testCase.retry_count || 0);
          setRetryInterval(testCase.retry_interval || 0);
          setPreScript(testCase.pre_script || '');
          setPostScript(testCase.post_script || '');
          setAuthType('none');
          setAuthToken('');
          setApiKeyName('');
          setApiKeyValue('');
          setBasicUser('');
          setBasicPass('');
          setSessionCookies([]);
          setResult(null);
          consoleRef.current?.clear();
          setSelectedProjectId(testCase.project_id ?? null);
          // 用例未绑定环境时保留顶部已选环境，避免打开用例后内网放行失效
          if (testCase.environment_id) {
            setSelectedEnvironmentId(testCase.environment_id);
          }
        })
        .catch((error: any) => {
          if (active) {
            message.error(error.message);
          }
        })
        .finally(() => {
          if (active) {
            setSourceCaseLoading(false);
          }
        });
      return () => {
        active = false;
      };
    }

    // 保留其他页面使用的简单参数预填兼容。
    const pMethod = searchParams.get('method');
    const pUrl = searchParams.get('url');
    const pHeaders = searchParams.get('headers');
    const pParams = searchParams.get('params');
    const pBody = searchParams.get('body');
    // 无 case_id 时视为「新建请求」，保存走 create
    setLoadedCaseId(null);
    if (pMethod) setMethod(pMethod);
    if (pUrl) setUrl(pUrl);
    if (pHeaders) {
      try { setHeaders(JSON.stringify(JSON.parse(pHeaders), null, 2)); } catch { setHeaders(pHeaders); }
    }
    if (pParams) {
      try { setParams(JSON.stringify(JSON.parse(pParams), null, 2)); } catch { setParams(pParams); }
    }
    if (pBody) {
      try { setBody(JSON.stringify(JSON.parse(pBody), null, 2)); } catch { setBody(pBody); }
    }
  }, [
    searchParams,
    setSelectedEnvironmentId,
    setSelectedProjectId,
    sourceCaseId,
  ]);

  // ---- 文件处理 ----
  function addFiles(files: FileList | File[] | null) {
    if (!files) return;
    const newItems: FileItem[] = Array.from(files).map((f) => ({
      file: f,
      field: 'file',
    }));
    setFileItems([...fileItems, ...newItems]);
  }

  function removeFile(idx: number) {
    setFileItems(fileItems.filter((_, i) => i !== idx));
  }

  function updateFileField(idx: number, field: string) {
    const next = [...fileItems];
    next[idx] = { ...next[idx], field };
    setFileItems(next);
  }

  // ---- 前置条件 ----
  function addPreRequest() {
    setPreRequests([
      ...preRequests,
      {
        name: `前置请求 ${preRequests.length + 1}`,
        method: 'POST',
        url: '',
        headers: {},
        params: {},
        body: {},
        extract_rules: [],
      },
    ]);
  }

  function updatePreRequest(idx: number, field: keyof PreRequestItem, value: any) {
    const next = [...preRequests];
    next[idx] = { ...next[idx], [field]: value };
    setPreRequests(next);
  }

  function removePreRequest(idx: number) {
    setPreRequests(preRequests.filter((_, i) => i !== idx));
  }

  function addPreExtractRule(preIdx: number) {
    const next = [...preRequests];
    next[preIdx].extract_rules.push({
      name: '',
      source: 'json_path',
      expression: '',
    });
    setPreRequests(next);
  }

  function updatePreExtractRule(preIdx: number, ruleIdx: number, field: string, value: any) {
    const next = [...preRequests];
    next[preIdx].extract_rules[ruleIdx] = {
      ...next[preIdx].extract_rules[ruleIdx],
      [field]: value,
    };
    setPreRequests(next);
  }

  function removePreExtractRule(preIdx: number, ruleIdx: number) {
    const next = [...preRequests];
    next[preIdx].extract_rules = next[preIdx].extract_rules.filter((_, i) => i !== ruleIdx);
    setPreRequests(next);
  }

  // ---- 断言 ----
  function addAssertion() {
    setAssertions([...assertions, {
      assertion_type: 'status_code', expression: '', operator: 'eq', expected: '200',
    }]);
  }

  /** A8：按模板追加一条断言（不覆盖已编辑的行，插入后字段仍可编辑） */
  function applyAssertionTemplate(templateKey: string) {
    const template = ASSERTION_TEMPLATES.find((item) => item.key === templateKey);
    if (!template) return;
    setAssertions([
      ...assertions,
      {
        assertion_type: template.assertion.assertion_type,
        expression: template.assertion.expression ?? '',
        operator: template.assertion.operator ?? 'eq',
        expected: template.assertion.expected ?? '',
      },
    ]);
  }
  function updateAssertion(index: number, field: string, value: any) {
    const next = [...assertions];
    next[index] = { ...next[index], [field]: value };
    setAssertions(next);
  }
  function removeAssertion(index: number) {
    setAssertions(assertions.filter((_, i) => i !== index));
  }

  function addExtractRule() {
    setExtractRules([
      ...extractRules,
      { name: '', source: 'json_path', expression: '' },
    ]);
  }

  function updateExtractRule(index: number, field: string, value: string) {
    setExtractRules(
      extractRules.map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, [field]: value } : rule
      )
    );
  }

  function removeExtractRule(index: number) {
    setExtractRules(extractRules.filter((_, ruleIndex) => ruleIndex !== index));
  }

  // ---- 请求配置解析（执行与保存共用，保证两条链路 payload 一致）----
  function parseRequestParts(): ParsedRequestParts {
    const parsedHeaders = parseHeadersJson(headers);
    const parsedParams = parseJsonObject(params, 'Params');
    let parsedBody: unknown;
    let graphqlQueryValue: string | undefined;

    if (bodyType === 'none') {
      parsedBody = undefined;
    } else if (bodyType === 'json') {
      parsedBody = parseJsonText(body, 'Body', { allowEmpty: true });
    } else if (bodyType === 'x-www-form-urlencoded') {
      parsedBody = parseJsonObject(formBody, '表单 Body');
      parsedHeaders['Content-Type'] = 'application/x-www-form-urlencoded';
    } else if (bodyType === 'graphql') {
      if (!graphqlQuery.trim()) {
        throw new Error('请填写 GraphQL query');
      }
      graphqlQueryValue = graphqlQuery.trim();
      // 后端约定：graphql_query 为语句，body 为 variables 对象
      parsedBody = parseJsonObject(graphqlVariables, 'GraphQL Variables');
      if (!hasHeader(parsedHeaders, 'Content-Type')) {
        parsedHeaders['Content-Type'] = 'application/json';
      }
    } else {
      // form-data 由「高级设置 → 文件上传」接管，这里不组装 body
      parsedBody = undefined;
    }

    return {
      headers: parsedHeaders,
      params: parsedParams,
      body: parsedBody,
      graphqlQuery: graphqlQueryValue,
    };
  }

  /** 当前认证配置 */
  function currentAuthConfig(): AuthConfig {
    return {
      type: authType,
      token: authToken || undefined,
      apiKeyName: apiKeyName || undefined,
      apiKeyValue: apiKeyValue || undefined,
      apiKeyIn,
      username: basicUser || undefined,
      password: basicPass || undefined,
    };
  }

  // ---- 取消请求 ----
  function handleCancelExecute() {
    if (!abortRef.current) return;
    abortRef.current.abort();
    abortRef.current = null;
    setExecuting(false);
    consoleRef.current?.log({ type: 'error', message: '请求已取消' });
    message.info('已取消本次请求');
  }

  // ---- 执行 ----
  async function handleExecute() {
    if (!url.trim()) {
      message.warning('请输入请求 URL');
      return;
    }
    let parts: ParsedRequestParts;
    let parsedVars: Record<string, unknown> = {};
    try {
      parts = parseRequestParts();
    } catch (error: any) {
      message.error(error.message || '请求配置解析失败');
      return;
    }
    try {
      const localVariables = parseJsonObject(envVariables, '环境变量');
      parsedVars = { ...workspaceVariables, ...localVariables };
    } catch (error: any) {
      message.error(error.message || '环境变量 JSON 格式不正确');
      return;
    }

    // 应用认证配置（合并到 headers / params）
    const applied = applyAuth(currentAuthConfig(), parts.headers, parts.params);
    const parsedHeaders = applied.headers;
    const parsedParams = applied.params;
    const parsedBody = parts.body;
    const graphqlQueryValue = parts.graphqlQuery;

    const controller = new AbortController();
    abortRef.current = controller;

    setExecuting(true);
    setResult(null);
    try {
      // 记录前置请求日志
      if (preRequests.length > 0) {
        preRequests.forEach((pre) => {
          consoleRef.current?.log({
            type: 'pre-request',
            method: pre.method,
            url: pre.url,
            message: `${pre.name}: ${pre.method} ${pre.url}`,
          });
        });
      }

      // 记录主请求日志
      consoleRef.current?.log({
        type: 'request',
        method,
        url,
        message: `${method} ${url}`,
      });

      let res;
      if (fileItems.length > 0) {
        res = await executionApi.runMultipart({
          method, url,
          headers: parsedHeaders, params: parsedParams, body: parsedBody,
          graphql_query: graphqlQueryValue,
          assertions, extract_rules: extractRules,
          variables: parsedVars, timeout,
          pre_requests: preRequests,
          cookies: sessionCookies,
          pre_script: preScript || undefined,
          post_script: postScript || undefined,
          retry_count: retryCount,
          retry_interval: retryInterval,
          project_id: selectedProjectId || undefined,
          environment_id: selectedEnvironment?.id || undefined,
          fileList: fileItems.map((f) => f.file),
          fileFields: fileItems.map((f) => f.field),
        }, { signal: controller.signal });
      } else {
        res = await executionApi.run({
          method, url,
          headers: parsedHeaders, params: parsedParams, body: parsedBody,
          graphql_query: graphqlQueryValue,
          assertions, extract_rules: extractRules,
          variables: parsedVars, timeout,
          pre_requests: preRequests,
          cookies: sessionCookies,
          pre_script: preScript || undefined,
          post_script: postScript || undefined,
          retry_count: retryCount,
          retry_interval: retryInterval,
          project_id: selectedProjectId || undefined,
          environment_id: selectedEnvironment?.id || undefined,
        }, { signal: controller.signal });
      }
      setResult(res.data);

      // 更新会话 Cookie
      if (res.data.session_cookies) {
        setSessionCookies(res.data.session_cookies);
      }

      // 记录响应日志
      if (res.data.response) {
        consoleRef.current?.log({
          type: 'response',
          method,
          url,
          statusCode: res.data.response.status_code,
          status: res.data.status,
          duration: res.data.duration,
          detail: res.data.response.body,
        });
      }

      // 记录断言日志
      if (res.data.assertion_results && res.data.assertion_results.length > 0) {
        res.data.assertion_results.forEach((a) => {
          consoleRef.current?.log({
            type: 'assertion',
            status: a.passed ? 'passed' : 'failed',
            message: `${a.assertion_type}: ${a.expression || ''} ${a.operator} ${a.expected || ''} → ${a.passed ? 'PASS' : 'FAIL'}`,
          });
        });
      }

      if (res.data.error_message) {
        consoleRef.current?.log({
          type: 'error',
          message: res.data.error_message,
        });
      }

      if (res.data.status === 'passed') message.success('测试通过');
      else if (res.data.status === 'failed') message.warning('断言未通过');
      else message.error('执行出错');

      // 执行成功（后端已写入 history）：刷新页内历史面板
      setHistoryRefreshKey((key) => key + 1);
    } catch (e: any) {
      // 主动取消：不弹错误提示，仅恢复初始态
      const cancelled =
        controller.signal.aborted
        || e?.code === 'ERR_CANCELED'
        || e?.name === 'CanceledError'
        || e?.message === 'canceled';
      if (cancelled) {
        consoleRef.current?.log({ type: 'error', message: '请求已取消' });
        return;
      }
      consoleRef.current?.log({
        type: 'error',
        message: e.message,
      });
      message.error(e.message);
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      setExecuting(false);
    }
  }

  // ---- 保存到接口列表 ----
  useEffect(() => {
    projectApi.listAll().then(res => setProjects(res.data || [])).catch(() => {});
  }, []);

  function openSaveModal() {
    if (!url.trim()) {
      message.warning('请先输入请求 URL');
      return;
    }
    // 自动生成默认标题：METHOD + URL 路径
    let path = url;
    try {
      const u = new URL(url);
      path = u.pathname;
    } catch {
      // Keep the raw URL when it is not absolute.
    }
    const defaultTitle = `${method} ${path}`;
    saveForm.setFieldsValue({
      title: defaultTitle,
      group_path: '',
      project_id: selectedProjectId || undefined,
    });
    setSaveModalOpen(true);
  }

  async function handleSave() {
    try {
      const values: any = await saveForm.validateFields();
      // 解析当前请求配置（与执行共用同一套解析逻辑）
      let parts: ParsedRequestParts;
      try {
        parts = parseRequestParts();
      } catch (error: any) {
        message.error(error.message || '请求配置解析失败');
        return;
      }
      const appliedAuth = applyAuth(currentAuthConfig(), parts.headers, parts.params);

      const payload = {
        title: values.title,
        method,
        url,
        headers: appliedAuth.headers,
        params: appliedAuth.params,
        body: parts.body,
        graphql_query: parts.graphqlQuery,
        group_path: values.group_path || undefined,
        project_id: values.project_id || selectedProjectId || undefined,
        environment_id: selectedEnvironment?.id || undefined,
        markers: ['quick_test'],
        extract_rules: extractRules,
        retry_count: retryCount,
        retry_interval: retryInterval,
        pre_script: preScript || undefined,
        post_script: postScript || undefined,
        assertions: assertions.length > 0 ? assertions.map((a, i) => ({
          assertion_type: a.assertion_type,
          expression: a.expression || null,
          operator: a.operator,
          expected: a.expected,
          priority: 'P1',
          order: i,
        })) : [{
          assertion_type: 'status_code',
          operator: 'eq',
          expected: '200',
          priority: 'P0',
          order: 0,
        }],
      };

      setSaving(true);
      if (loadedCaseId) {
        // 由 case_id 载入的用例：原地更新，避免重复创建
        await testCaseApi.update(loadedCaseId, payload);
        message.success('已更新');
        setSaveModalOpen(false);
        return;
      }

      await testCaseApi.create(payload);
      message.success('已保存到接口列表');
      setSaveModalOpen(false);
      // 提示是否跳转
      Modal.confirm({
        title: '保存成功',
        content: '是否立即跳转到接口列表查看？',
        okText: '去查看',
        cancelText: '继续测试',
        onOk: () => navigate('/api-list'),
      });
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  // ---- cURL 互通 ----
  /** 把导入/回填得到的 body 分派到对应 Body 类型 */
  function applyIncomingBody(incoming: unknown) {
    if (incoming === null || incoming === undefined || incoming === '') {
      setBodyType('none');
      return;
    }
    if (typeof incoming === 'string') {
      const formValues = parseUrlEncodedBody(incoming);
      if (formValues) {
        setFormBody(JSON.stringify(formValues, null, 2));
        setBodyType('x-www-form-urlencoded');
        return;
      }
      setBody(incoming);
      setBodyType('json');
      return;
    }
    setBody(JSON.stringify(incoming, null, 2));
    setBodyType('json');
  }

  async function handleCopyCurl() {
    if (!url.trim()) {
      message.warning('请先输入请求 URL');
      return;
    }
    try {
      const parts = parseRequestParts();
      const applied = applyAuth(currentAuthConfig(), parts.headers, parts.params);
      const command = toCurl({
        method,
        url,
        headers: applied.headers,
        params: applied.params,
        body: parts.body,
      });
      await copyTextToClipboard(command);
      message.success('cURL 已复制到剪贴板');
    } catch (error: any) {
      message.error(error?.message || '生成 cURL 失败');
    }
  }

  function handleImportedCurl(parsed: { method: string; url: string; headers: Record<string, string>; body?: unknown }) {
    setMethod(parsed.method || 'GET');
    setUrl(parsed.url);
    setHeaders(
      Object.keys(parsed.headers).length > 0
        ? JSON.stringify(parsed.headers, null, 2)
        : '{}'
    );
    applyIncomingBody(parsed.body);
    setCurlModalOpen(false);
    message.success('已从 cURL 回填请求，可点击「发送」执行');
  }

  // ---- 历史面板回填 ----
  function handleRestoreHistory(record: CallHistoryRecord) {
    // 历史记录不是「已载入的用例」，保存时仍走 create
    setLoadedCaseId(null);
    if (record.method) setMethod(record.method);
    if (record.url) setUrl(record.url);
    setHeaders(JSON.stringify(record.headers || {}, null, 2));
    setParams(JSON.stringify(record.params || {}, null, 2));
    applyIncomingBody(record.body);
    setResult(null);
  }

  return (
    <div className="quick-test-workspace" data-testid="quick-test-workspace">
      <aside className="quick-test-history-pane" aria-label="历史调用记录">
        <HistoryPanel
          projectId={selectedProjectId}
          refreshKey={historyRefreshKey}
          onRestore={handleRestoreHistory}
        />
      </aside>

      <div className="quick-test-main-pane">
      <Card
        className="quick-test-request-card"
        title={
          <Space>
            <ThunderboltOutlined /><span>快速测试</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              文件上传 · 前置条件 · 变量提取
            </span>
          </Space>
        }
        extra={
          <Space wrap size={8}>
            <Tooltip title="把当前请求转换成 cURL 命令并复制">
              <Button
                icon={<CopyOutlined />}
                onClick={handleCopyCurl}
                data-testid="copy-curl-btn"
              >
                复制 cURL
              </Button>
            </Tooltip>
            <Button
              icon={<ImportOutlined />}
              onClick={() => setCurlModalOpen(true)}
              data-testid="import-curl-btn"
            >
              导入 cURL
            </Button>
            <Button
              icon={<SaveOutlined />}
              onClick={openSaveModal}
              size="large"
              data-testid="save-btn"
              disabled={sourceCaseLoading}
            >
              {loadedCaseId ? '更新用例' : '保存到接口列表'}
            </Button>
            {executing ? (
              <Button
                danger
                icon={<CloseCircleOutlined />}
                onClick={handleCancelExecute}
                size="large"
                data-testid="cancel-btn"
              >
                取消
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={sourceCaseLoading}
                onClick={handleExecute}
                size="large"
                data-testid="send-btn"
              >
                发送请求
              </Button>
            )}
          </Space>
        }
      >
        {selectedEnvironment && (
          <div className="quick-test-environment-context" data-testid="quick-test-environment-context">
            <div className="quick-test-environment-primary">
              <Tag color="blue">当前环境</Tag>
              <strong>{selectedEnvironment.name}</strong>
              <code>{selectedEnvironment.base_url || '未配置 Base URL'}</code>
              <span>仅用于相对 URL 前缀，不作为可引用变量</span>
            </div>
            <span className="quick-test-environment-summary">
              提供 {Object.keys(selectedEnvironment.variables || {}).length} 个环境变量（可用占位符引用，本页可覆盖同名值）；
              <code>base_url</code> 仅用于相对 URL 前缀，不可引用
            </span>
          </div>
        )}

        {/* 请求行 */}
        <div className="quick-test-request-row">
          <Select value={method} onChange={setMethod} data-testid="method-select"
            options={METHODS.map((m) => ({ label: m, value: m }))} />
          {/* A9：URL 支持 {{ 变量提示；Input 作为 AutoComplete 的子元素，保留原 onPressEnter / testid */}
          <AutoComplete
            className="quick-test-url-input"
            value={url}
            options={urlSuggestions}
            filterOption={false}
            popupMatchSelectWidth={false}
            onChange={(value) => setUrl(value ?? '')}
          >
            <Input
              placeholder="https://api.example.com/users"
              data-testid="url-input"
              onPressEnter={handleExecute}
            />
          </AutoComplete>
          <span className="quick-test-timeout-label" style={{ color: '#6b7280' }}>超时(s):</span>
          <InputNumber value={timeout} onChange={(v) => setTimeoutVal(v || 30)} min={1} max={300} />
        </div>

        {(() => {
          const workspacePanels = [
            // ---- 文件上传 ----
            {
              key: 'files',
              label: <span><InboxOutlined /> 文件上传 ({fileItems.length})</span>,
              children: (
                <div>
                  <Dragger
                    beforeUpload={(file) => {
                      addFiles([file]);
                      return false; // 阻止自动上传
                    }}
                    multiple
                    showUploadList={false}
                  >
                    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                    <p className="ant-upload-text">点击或拖拽文件到此处</p>
                    <p className="ant-upload-hint">支持单个或多个文件上传，上传后可设置字段名</p>
                  </Dragger>

                  {fileItems.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                            <th style={{ textAlign: 'left', padding: '8px 12px', width: 150 }}>字段名 (field)</th>
                            <th style={{ textAlign: 'left', padding: '8px 12px' }}>文件名</th>
                            <th style={{ textAlign: 'left', padding: '8px 12px', width: 100 }}>大小</th>
                            <th style={{ width: 60 }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {fileItems.map((item, idx) => (
                            <tr key={idx} style={{ borderBottom: '1px solid #f3f4f6' }}>
                              <td style={{ padding: '8px 12px' }}>
                                <Input size="small" value={item.field}
                                  onChange={(e) => updateFileField(idx, e.target.value)}
                                  placeholder="file" />
                              </td>
                              <td style={{ padding: '8px 12px' }}>{item.file.name}</td>
                              <td style={{ padding: '8px 12px', color: '#6b7280' }}>
                                {(item.file.size / 1024).toFixed(1)} KB
                              </td>
                              <td style={{ textAlign: 'center' }}>
                                <Button type="link" danger size="small" icon={<DeleteOutlined />}
                                  onClick={() => removeFile(idx)} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div style={{ marginTop: 12, padding: 12, background: '#f9fafb', borderRadius: 6, fontSize: 13, color: '#6b7280' }}>
                    提示：上传文件后，主请求将以 multipart/form-data 方式发送。Body 字段将作为表单字段一起提交。
                  </div>
                </div>
              ),
            },
            // ---- 前置条件 ----
            {
              key: 'pre-requests',
              label: <span><LinkOutlined /> 前置条件 ({preRequests.length})</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 12, padding: 12, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    前置条件在主请求之前按顺序执行。从前置请求响应中提取的变量（如 token、id）会自动注入到后续请求中，
                    使用 <code style={{ background: '#dbeafe', padding: '2px 6px', borderRadius: 4 }}>{'{{var_name}}'}</code> 语法引用。
                  </div>

                  {preRequests.length === 0 ? (
                    <Empty description="暂无前置条件" style={{ padding: 20 }} />
                  ) : (
                    <Collapse
                      items={preRequests.map((pre, preIdx) => ({
                        key: String(preIdx),
                        label: (
                          <Space>
                            <Tag color={methodColor[pre.method] || 'default'}>{pre.method}</Tag>
                            <span style={{ fontWeight: 500 }}>{pre.name}</span>
                            <span style={{ color: '#6b7280' }}>{pre.url || '(未设置 URL)'}</span>
                          </Space>
                        ),
                        extra: (
                          <Button type="link" danger size="small" icon={<DeleteOutlined />}
                            onClick={(e) => { e.stopPropagation(); removePreRequest(preIdx); }}>
                            删除
                          </Button>
                        ),
                        children: (
                          <div>
                            <Space style={{ width: '100%', marginBottom: 12 }} size="small">
                              <Input size="small" value={pre.name}
                                onChange={(e) => updatePreRequest(preIdx, 'name', e.target.value)}
                                placeholder="名称" style={{ width: 150 }} />
                              <Select size="small" value={pre.method}
                                onChange={(v) => updatePreRequest(preIdx, 'method', v)}
                                style={{ width: 100 }}
                                options={METHODS.map((m) => ({ label: m, value: m }))} />
                              <Input size="small" value={pre.url}
                                onChange={(e) => updatePreRequest(preIdx, 'url', e.target.value)}
                                placeholder="https://api.example.com/login" style={{ flex: 1, minWidth: 300 }} />
                            </Space>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                              <div>
                                <label style={{ fontSize: 12, color: '#6b7280' }}>Headers (JSON)</label>
                                <TextArea rows={2} size="small"
                                  value={JSON.stringify(pre.headers || {}, null, 0)}
                                  onChange={(e) => {
                                    try { updatePreRequest(preIdx, 'headers', JSON.parse(e.target.value)); } catch {
                                      // Keep the last valid JSON value while editing.
                                    }
                                  }}
                                  placeholder='{"Content-Type": "application/json"}' />
                              </div>
                              <div>
                                <label style={{ fontSize: 12, color: '#6b7280' }}>Body (JSON)</label>
                                <TextArea rows={2} size="small"
                                  value={JSON.stringify(pre.body || {}, null, 0)}
                                  onChange={(e) => {
                                    try { updatePreRequest(preIdx, 'body', JSON.parse(e.target.value)); } catch {
                                      // Keep the last valid JSON value while editing.
                                    }
                                  }}
                                  placeholder='{"username": "admin"}' />
                              </div>
                            </div>

                            {/* 变量提取规则 */}
                            <div style={{ marginTop: 12 }}>
                              <div style={{ marginBottom: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <label style={{ fontSize: 12, color: '#6b7280' }}>
                                  <KeyOutlined /> 变量提取规则
                                </label>
                                <Button size="small" type="dashed" icon={<PlusOutlined />}
                                  onClick={() => addPreExtractRule(preIdx)}>添加提取</Button>
                              </div>
                              {pre.extract_rules.map((rule, ruleIdx) => (
                                <Space key={ruleIdx} size="small" style={{ display: 'flex', marginBottom: 4 }}>
                                  <Input size="small" value={rule.name}
                                    onChange={(e) => updatePreExtractRule(preIdx, ruleIdx, 'name', e.target.value)}
                                    placeholder="变量名 (如 token)" style={{ width: 120 }} />
                                  <Select size="small" value={rule.source}
                                    onChange={(v) => updatePreExtractRule(preIdx, ruleIdx, 'source', v)}
                                    style={{ width: 110 }}
                                    options={EXTRACT_SOURCES.map((s) => ({ label: s, value: s }))} />
                                  <Input size="small" value={rule.expression}
                                    onChange={(e) => updatePreExtractRule(preIdx, ruleIdx, 'expression', e.target.value)}
                                    placeholder="表达式 (如 $.data.token)" style={{ width: 200 }} />
                                  <Button type="link" danger size="small" icon={<DeleteOutlined />}
                                    onClick={() => removePreExtractRule(preIdx, ruleIdx)} />
                                </Space>
                              ))}
                            </div>
                          </div>
                        ),
                      }))}
                    />
                  )}

                  <Button type="dashed" onClick={addPreRequest} block style={{ marginTop: 12 }} icon={<PlusOutlined />}>
                    添加前置请求
                  </Button>
                </div>
              ),
            },
            // ---- 断言规则 ----
            {
              key: 'assertions',
              label: `断言规则 (${assertions.length})`,
              children: (
                <div>
                  {/* A8：常用断言模板，点击插入一条新断言（不覆盖已有行） */}
                  <div className="quick-test-assertion-templates">
                    <span className="quick-test-editor-summary">常用断言：</span>
                    <Space size={4} wrap>
                      {ASSERTION_TEMPLATES.map((template) => (
                        <Tooltip key={template.key} title={template.hint}>
                          <Button
                            size="small"
                            onClick={() => applyAssertionTemplate(template.key)}
                            data-testid={`assertion-template-${template.key}`}
                          >
                            {template.label}
                          </Button>
                        </Tooltip>
                      ))}
                    </Space>
                  </div>

                  {assertions.map((a, idx) => (
                    <Space key={idx} align="baseline" wrap style={{ marginBottom: 8 }}>
                      <Select value={a.assertion_type}
                        onChange={(v) => updateAssertion(idx, 'assertion_type', v)}
                        style={{ width: 140 }}
                        options={ASSERTION_TYPES.map((t) => ({ label: t, value: t }))} />
                      <Input value={a.expression}
                        onChange={(e) => updateAssertion(idx, 'expression', e.target.value)}
                        placeholder="表达式" style={{ width: 180 }} />
                      <Select value={a.operator}
                        onChange={(v) => updateAssertion(idx, 'operator', v)}
                        style={{ width: 110 }}
                        options={OPERATORS.map((o) => ({ label: o, value: o }))} />
                      <Input value={a.expected}
                        onChange={(e) => updateAssertion(idx, 'expected', e.target.value)}
                        placeholder="期望值" style={{ width: 120 }} />
                      <Button type="link" danger onClick={() => removeAssertion(idx)}>删除</Button>
                    </Space>
                  ))}
                  <Button type="dashed" onClick={addAssertion} block>+ 添加断言</Button>

                  <Divider />
                  <div style={{ marginBottom: 8, fontWeight: 600 }}>失败重试</div>
                  <Space wrap>
                    <span>重试次数</span>
                    <InputNumber
                      min={0}
                      max={10}
                      value={retryCount}
                      onChange={(value) => setRetryCount(value || 0)}
                    />
                    <span>间隔（秒）</span>
                    <InputNumber
                      min={0}
                      max={300}
                      step={0.5}
                      value={retryInterval}
                      onChange={(value) => setRetryInterval(value || 0)}
                    />
                  </Space>

                  <Divider />
                  <div style={{ marginBottom: 8, fontWeight: 600 }}>
                    响应变量提取
                  </div>
                  {extractRules.map((rule, index) => (
                    <Space key={index} align="baseline" wrap style={{ marginBottom: 8 }}>
                      <Input
                        value={rule.name}
                        onChange={(event) =>
                          updateExtractRule(index, 'name', event.target.value)
                        }
                        placeholder="变量名"
                        style={{ width: 150 }}
                      />
                      <Select
                        value={rule.source}
                        onChange={(value) =>
                          updateExtractRule(index, 'source', value)
                        }
                        style={{ width: 130 }}
                        options={EXTRACT_SOURCES.map((source) => ({
                          label: source,
                          value: source,
                        }))}
                      />
                      <Input
                        value={rule.expression}
                        onChange={(event) =>
                          updateExtractRule(index, 'expression', event.target.value)
                        }
                        placeholder="JSONPath / Header / 正则表达式"
                        style={{ width: 260 }}
                      />
                      <Button
                        type="link"
                        danger
                        onClick={() => removeExtractRule(index)}
                      >
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button type="dashed" onClick={addExtractRule} block>
                    + 添加提取规则
                  </Button>
                </div>
              ),
            },
            // ---- 环境变量 ----
            {
              key: 'variables',
              label: <span><KeyOutlined /> 环境变量</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#f0fdf4', borderRadius: 6, fontSize: 13, color: '#166534' }}>
                    当前工作区环境的环境变量会自动作为默认值，<code>base_url</code> 仅用于拼接相对 URL，不作为可引用变量。
                    此处填写的变量会覆盖同名环境变量，并与前置条件提取结果一起用于渲染 <code>{'{{var}}'}</code> 占位符。
                  </div>
                  <TextArea rows={6} value={envVariables} onChange={(e) => setEnvVariables(e.target.value)}
                    placeholder='{"token": "xxx", "timeout": "3000"}' />
                </div>
              ),
            },
            // ---- 认证配置 ----
            {
              key: 'auth',
              label: <span><LockOutlined /> 认证配置</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 12, padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    选择认证类型后自动将认证信息添加到请求头或查询参数。纯前端组装，发送时合并到 headers/params。
                  </div>
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>认证类型</label>
                    <Select
                      value={authType}
                      onChange={setAuthType}
                      style={{ width: 240 }}
                      data-testid="auth-type-select"
                      options={[
                        { label: '无', value: 'none' },
                        { label: 'Bearer Token', value: 'bearer' },
                        { label: 'OAuth2', value: 'oauth2' },
                        { label: 'API Key', value: 'api_key' },
                        { label: 'Basic Auth', value: 'basic' },
                      ]}
                    />
                  </div>

                  {authType === 'bearer' && (
                    <div style={{ marginBottom: 12 }}>
                      <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Token</label>
                      <Input value={authToken} onChange={(e) => setAuthToken(e.target.value)}
                        placeholder="Bearer Token 值" />
                    </div>
                  )}

                  {authType === 'oauth2' && (
                    <div style={{ marginBottom: 12 }}>
                      <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Access Token</label>
                      <Input value={authToken} onChange={(e) => setAuthToken(e.target.value)}
                        placeholder="OAuth2 Access Token" />
                    </div>
                  )}

                  {authType === 'api_key' && (
                    <div style={{ marginBottom: 12 }}>
                      <Space style={{ width: '100%' }} size="middle">
                        <div style={{ flex: 1 }}>
                          <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Key 名</label>
                          <Input value={apiKeyName} onChange={(e) => setApiKeyName(e.target.value)}
                            placeholder="如 X-API-Key" />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Value</label>
                          <Input value={apiKeyValue} onChange={(e) => setApiKeyValue(e.target.value)}
                            placeholder="API Key 值" />
                        </div>
                        <div style={{ width: 140 }}>
                          <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>位置</label>
                          <Select value={apiKeyIn} onChange={setApiKeyIn} style={{ width: '100%' }}
                            options={[{ label: 'Header', value: 'header' }, { label: 'Query', value: 'query' }]} />
                        </div>
                      </Space>
                    </div>
                  )}

                  {authType === 'basic' && (
                    <Space style={{ width: '100%' }} size="middle">
                      <div style={{ flex: 1 }}>
                        <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>用户名</label>
                        <Input value={basicUser} onChange={(e) => setBasicUser(e.target.value)}
                          placeholder="username" />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>密码</label>
                        <Input.Password value={basicPass} onChange={(e) => setBasicPass(e.target.value)}
                          placeholder="password" />
                      </div>
                    </Space>
                  )}

                  {authType === 'none' && (
                    <Empty description="未启用认证" style={{ padding: 20 }} />
                  )}
                </div>
              ),
            },
            // ---- 前后置脚本 ----
            {
              key: 'scripts',
              label: <span><CodeOutlined /> 前后置脚本</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 8, fontWeight: 600 }}>前置脚本 (Python)</div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#eff6ff', borderRadius: 6, fontSize: 13, color: '#1e40af' }}>
                    主请求执行前运行，可访问 <code>variables</code> 与 <code>request</code>。修改 variables 可影响请求变量渲染。
                  </div>
                  <TextArea rows={5} value={preScript} onChange={(e) => setPreScript(e.target.value)}
                    placeholder={'# 示例\nvariables["trace_id"] = "abc123"\nprint("前置脚本")'}
                    style={{ fontFamily: 'monospace', fontSize: 13, marginBottom: 16 }} data-testid="pre-script-input" />

                  <div style={{ marginBottom: 8, fontWeight: 600 }}>后置脚本 (Python)</div>
                  <div style={{ marginBottom: 8, padding: 10, background: '#f0fdf4', borderRadius: 6, fontSize: 13, color: '#166534' }}>
                    主请求执行后运行，可访问 <code>response</code>（status_code/headers/body/text）与 <code>variables</code>。
                  </div>
                  <TextArea rows={5} value={postScript} onChange={(e) => setPostScript(e.target.value)}
                    placeholder={'# 示例\nif response and response["status_code"] == 200:\n    print("成功")'}
                    style={{ fontFamily: 'monospace', fontSize: 13 }} data-testid="post-script-input" />
                </div>
              ),
            },
            // ---- 会话 Cookie ----
            {
              key: 'cookies',
              label: <span><KeyOutlined /> Cookie ({sessionCookies.length})</span>,
              children: (
                <div data-testid="cookie-panel">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                    <div style={{ padding: 10, background: '#fff7ed', borderRadius: 6, fontSize: 13, color: '#9a3412', flex: 1, marginRight: 12 }}>
                      请求执行后自动捕获响应的 Set-Cookie，下次请求自动带上。Cookie 在当前调试会话内保持。
                    </div>
                    {sessionCookies.length > 0 && (
                      <Button danger icon={<DeleteOutlined />} onClick={() => setSessionCookies([])}>
                        清除全部
                      </Button>
                    )}
                  </div>
                  {sessionCookies.length === 0 ? (
                    <Empty description="暂无会话 Cookie，发送请求后自动捕获" style={{ padding: 20 }} />
                  ) : (
                    <Table
                      dataSource={sessionCookies}
                      rowKey="name"
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '名称', dataIndex: 'name', width: 160,
                          render: (v: string) => <code style={{ fontWeight: 600 }}>{v}</code> },
                        { title: '值', dataIndex: 'value', ellipsis: true,
                          render: (v: string) => <code>{v}</code> },
                        { title: '路径', dataIndex: 'path', width: 100,
                          render: (v: string) => v || '-' },
                        { title: '域名', dataIndex: 'domain', width: 160,
                          render: (v: string) => v || '-' },
                        { title: '', width: 60,
                          render: (_, c) => (
                            <Button type="link" danger size="small" icon={<DeleteOutlined />}
                              onClick={() => setSessionCookies(sessionCookies.filter((x) => x.name !== c.name))} />
                          ) },
                      ]}
                    />
                  )}
                </div>
              ),
            },
          ];
          const panelByKey = Object.fromEntries(
            workspacePanels.map((panel) => [panel.key, panel]),
          ) as Record<string, (typeof workspacePanels)[number]>;
          const advancedCount = fileItems.length
            + preRequests.length
            + sessionCookies.length
            + (envVariables.trim() && envVariables.trim() !== '{}' ? 1 : 0)
            + (preScript.trim() ? 1 : 0)
            + (postScript.trim() ? 1 : 0);

          return (
            <>
              <Tabs
                className="quick-test-core-tabs"
                tabBarExtraContent={
                  /* A9：当前可用变量查看入口（不阻塞请求区） */
                  <VariablesPopover
                    entries={quickTestVariables.entries}
                    names={variableNames}
                    loading={quickTestVariables.loading}
                    error={quickTestVariables.error}
                    pageVariablesValid={quickTestVariables.pageVariablesValid}
                    environmentName={selectedEnvironment?.name}
                    onReload={() => void quickTestVariables.reload()}
                  />
                }
                items={[
                  {
                    key: 'params',
                    label: 'Params',
                    children: (
                      <JsonKeyValueEditor
                        value={params}
                        onChange={setParams}
                        keyPlaceholder="参数名"
                        valuePlaceholder="参数值"
                        rawPlaceholder='{"page": 1, "size": 20}'
                        variableNames={variableNames}
                      />
                    ),
                  },
                  {
                    key: 'headers',
                    label: 'Headers',
                    children: (
                      <JsonKeyValueEditor
                        value={headers}
                        onChange={setHeaders}
                        keyPlaceholder="Header 名"
                        valuePlaceholder="Header 值"
                        rawPlaceholder='{"Content-Type": "application/json"}'
                        valueMode="string"
                        variableNames={variableNames}
                      />
                    ),
                  },
                  {
                    key: 'body',
                    label: 'Body',
                    children: (
                      <RequestBodyEditor
                        bodyType={bodyType}
                        onBodyTypeChange={setBodyType}
                        jsonBody={body}
                        onJsonBodyChange={setBody}
                        formBody={formBody}
                        onFormBodyChange={setFormBody}
                        graphqlQuery={graphqlQuery}
                        onGraphqlQueryChange={setGraphqlQuery}
                        graphqlVariables={graphqlVariables}
                        onGraphqlVariablesChange={setGraphqlVariables}
                        onOpenFileUpload={() => {
                          setAdvancedKeys(['advanced']);
                          setAdvancedTabKey('files');
                        }}
                        variableNames={variableNames}
                      />
                    ),
                  },
                  {
                    ...panelByKey.auth,
                    key: 'auth',
                    label: 'Auth',
                  },
                  {
                    ...panelByKey.assertions,
                    key: 'tests',
                    label: `Tests (${assertions.length})`,
                  },
                ]}
              />

              <Collapse
                className="quick-test-advanced-settings"
                activeKey={advancedKeys}
                onChange={(keys) =>
                  setAdvancedKeys(Array.isArray(keys) ? keys.map(String) : [String(keys)])
                }
                items={[
                  {
                    key: 'advanced',
                    label: (
                      <Space size="small">
                        <span>高级设置</span>
                        {advancedCount > 0 && <Tag color="blue">{advancedCount}</Tag>}
                        <span className="quick-test-advanced-hint">
                          文件、前置请求、变量、脚本与 Cookie
                        </span>
                      </Space>
                    ),
                    children: (
                      <Tabs
                        size="small"
                        activeKey={advancedTabKey}
                        onChange={setAdvancedTabKey}
                        items={[
                          panelByKey.files,
                          panelByKey['pre-requests'],
                          panelByKey.variables,
                          panelByKey.scripts,
                          panelByKey.cookies,
                        ]}
                      />
                    ),
                  },
                ]}
              />
            </>
          );
        })()}
      </Card>

      <section className="quick-test-output-section" aria-label="响应与执行结果">
        <div className="quick-test-output-header">
          <div>
            <h2>响应与执行</h2>
            <span>请求结果、断言、提取变量与调试日志</span>
          </div>
          {result && !executing && (
            <Space size="small">
              <Tag color={statusColor[result.status] || 'default'}>{result.status}</Tag>
              <span>{result.duration.toFixed(3)}s</span>
            </Space>
          )}
        </div>

        {!executing && !result && (
          <div className="quick-test-output-empty">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="发送请求后在此查看响应和测试结果"
            />
          </div>
        )}

      {/* 前置条件执行结果 */}
      {result && (result as any).pre_request_results && (result as any).pre_request_results.length > 0 && (
        <Card title="前置条件执行结果" size="small">
          <Table
            dataSource={(result as any).pre_request_results}
            rowKey="index"
            pagination={false}
            size="small"
            columns={[
              {
                title: '状态', dataIndex: 'success', width: 60,
                render: (s: boolean) => s ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>,
              },
              { title: '名称', dataIndex: 'name', width: 150 },
              { title: '状态码', dataIndex: 'status_code', width: 80,
                render: (v: any) => v || '-' },
              { title: '耗时', dataIndex: 'elapsed', width: 80,
                render: (v: number) => v ? `${v}s` : '-' },
              {
                title: '提取的变量', dataIndex: 'extracted_variables',
                render: (vars: any) => {
                  const entries = Object.entries(vars || {});
                  if (entries.length === 0) return '-';
                  return entries.map(([k, v]) => (
                    <Tag key={k} color="blue">
                      <code>{k}</code> = <code>{String(v).substring(0, 40)}</code>
                    </Tag>
                  ));
                },
              },
              { title: '错误', dataIndex: 'error', render: (v: string) => v ?
                <span style={{ color: '#dc2626' }}>{v}</span> : '-' },
            ]}
          />
        </Card>
      )}

      {/* 主请求执行结果 */}
      {executing && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin size="large" description="正在发送请求..." />
        </Card>
      )}

      {result && !executing && (
        <Card
          style={{ marginTop: 16 }}
          title={
            <Space>
              <span>执行结果</span>
              <Tag color={statusColor[result.status] || 'default'} style={{ fontSize: 14 }}>{result.status}</Tag>
              <span style={{ color: '#6b7280', fontWeight: 400 }}>耗时 {result.duration.toFixed(3)}s</span>
            </Space>
          }
        >
          {result.error_message ? (
            <pre style={{ background: '#fef2f2', color: '#dc2626', padding: 12, borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap' }}>
              {result.error_message}
            </pre>
          ) : null}

          {result.response && <ResponseViewer response={result.response} />}

          {result.assertion_results && result.assertion_results.length > 0 && (
            <Card type="inner" title="断言结果" style={{ marginBottom: 16 }}>
              <Table
                dataSource={result.assertion_results}
                rowKey={(record) => JSON.stringify(record)}
                pagination={false} size="small"
                columns={[
                  { title: '结果', dataIndex: 'passed', width: 60,
                    render: (p: boolean) => p ? <Tag color="green">PASS</Tag> : <Tag color="red">FAIL</Tag> },
                  { title: '类型', dataIndex: 'assertion_type', width: 120 },
                  { title: '表达式', dataIndex: 'expression', render: (v: string) => v || '-' },
                  { title: '操作符', dataIndex: 'operator', width: 80 },
                  { title: '期望值', dataIndex: 'expected', width: 80,
                    render: (v: any) => v !== null && v !== undefined ? String(v) : '-' },
                  { title: '实际值', dataIndex: 'actual', width: 80,
                    render: (v: any) => v !== null && v !== undefined ? String(v) : '-' },
                  { title: '说明', dataIndex: 'message', render: (v: string) => v || '-' },
                ]}
              />
            </Card>
          )}

          {result.extracted_variables && result.extracted_variables.length > 0 && (
            <Card type="inner" title="提取的变量">
              <Table
                dataSource={result.extracted_variables}
                rowKey="name" pagination={false} size="small"
                columns={[
                  { title: '变量名', dataIndex: 'name' },
                  { title: '值', dataIndex: 'value',
                    render: (v: any) => (
                      <code style={{ background: '#f3f4f6', padding: '2px 6px', borderRadius: 4 }}>
                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                      </code>
                    ) },
                  { title: '来源', dataIndex: 'source', width: 80 },
                ]}
              />
            </Card>
          )}

          {/* 重试记录 */}
          {result.retry_attempts && result.retry_attempts.length > 1 && (
            <Card type="inner" title="重试记录" style={{ marginBottom: 16 }}>
              <Table
                dataSource={result.retry_attempts}
                rowKey="attempt" pagination={false} size="small"
                columns={[
                  { title: '尝试次数', dataIndex: 'attempt', width: 90 },
                  { title: '状态', dataIndex: 'status', width: 90,
                    render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag> },
                  { title: '状态码', dataIndex: 'status_code', width: 90,
                    render: (c: number) => c || '-' },
                  { title: '耗时(s)', dataIndex: 'duration', width: 90,
                    render: (d: number) => d ? d.toFixed(3) : '-' },
                  { title: '错误', dataIndex: 'error', render: (e: string) => e ?
                    <span style={{ color: '#dc2626' }}>{e}</span> : '-' },
                ]}
              />
            </Card>
          )}

          {/* 脚本执行结果 */}
          {(result.pre_script_result || result.post_script_result) && (
            <Card type="inner" title="脚本执行结果" style={{ marginBottom: 16 }}>
              {result.pre_script_result && (
                <div style={{ marginBottom: 12 }}>
                  <Space>
                    <span style={{ fontWeight: 600 }}>前置脚本：</span>
                    <Tag color={result.pre_script_result.success ? 'green' : 'red'}>
                      {result.pre_script_result.success ? '成功' : '失败'}
                    </Tag>
                  </Space>
                  {result.pre_script_result.output && (
                    <pre style={{ background: '#0f172a', color: '#e2e8f0', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.pre_script_result.output}
                    </pre>
                  )}
                  {result.pre_script_result.error && (
                    <pre style={{ background: '#fef2f2', color: '#dc2626', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.pre_script_result.error}
                    </pre>
                  )}
                </div>
              )}
              {result.post_script_result && (
                <div>
                  <Space>
                    <span style={{ fontWeight: 600 }}>后置脚本：</span>
                    <Tag color={result.post_script_result.success ? 'green' : 'red'}>
                      {result.post_script_result.success ? '成功' : '失败'}
                    </Tag>
                  </Space>
                  {result.post_script_result.output && (
                    <pre style={{ background: '#0f172a', color: '#e2e8f0', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.post_script_result.output}
                    </pre>
                  )}
                  {result.post_script_result.error && (
                    <pre style={{ background: '#fef2f2', color: '#dc2626', padding: 8, borderRadius: 6, fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {result.post_script_result.error}
                    </pre>
                  )}
                </div>
              )}
            </Card>
          )}
        </Card>
      )}

        {/* Console 窗口 */}
        <Collapse
          className="quick-test-console-collapse"
          defaultActiveKey={[]}
          items={[
            {
              key: 'console',
              label: 'Console',
              forceRender: true,
              children: <ConsoleWindow ref={consoleRef} height={260} />,
            },
          ]}
        />
      </section>
      </div>

      {/* 导入 cURL */}
      <CurlImportModal
        open={curlModalOpen}
        onCancel={() => setCurlModalOpen(false)}
        onImport={handleImportedCurl}
      />

      {/* 保存到接口列表 / 更新用例 Modal */}
      <Modal
        title={loadedCaseId ? '更新用例' : '保存到接口列表'}
        open={saveModalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setSaveModalOpen(false)}
        width={520}
        destroyOnHidden
      >
        <div style={{ marginBottom: 16, padding: 12, background: '#f9fafb', borderRadius: 6, fontSize: 13 }}>
          <Space>
            <Tag color={methodColor[method] || 'default'} style={{ minWidth: 50, textAlign: 'center' }}>{method}</Tag>
            <span style={{ color: '#6b7280', wordBreak: 'break-all' }}>{url}</span>
          </Space>
        </div>
        <Form form={saveForm} layout="vertical">
          <Form.Item name="title" label="用例标题" rules={[{ required: true, message: '请输入用例标题' }]}>
            <Input placeholder="如：获取用户列表" />
          </Form.Item>
          <Form.Item name="group_path" label="模块/分组">
            <Input placeholder="如：用户管理（可选）" />
          </Form.Item>
          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              options={projects.map(p => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
        </Form>
        <div style={{ color: '#9ca3af', fontSize: 12 }}>
          {loadedCaseId
            ? '将覆盖当前用例的 Headers、Params、Body、认证、提取规则和断言。会话 Cookie 不会写入用例。'
            : '当前的 Headers、Params、Body、认证、提取规则和断言将一并保存。会话 Cookie 不会写入用例；长期 Cookie 请配置到当前环境。'}
        </div>
      </Modal>
    </div>
  );
}
