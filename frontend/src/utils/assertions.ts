/** HTTP 响应断言的类型、操作符与表单值转换（执行引擎 assertion_engine 支持的类型）.*/

export interface AssertionTypeMeta {
  value: string;
  label: string;
  needsExpression: boolean;
}

export const ASSERTION_TYPES: AssertionTypeMeta[] = [
  { value: 'status_code', label: '状态码', needsExpression: false },
  { value: 'json_path', label: 'JSONPath', needsExpression: true },
  { value: 'header', label: '响应头', needsExpression: true },
  { value: 'response_time', label: '响应耗时(秒)', needsExpression: false },
  { value: 'json_schema', label: 'JSON Schema', needsExpression: false },
];

export const ASSERTION_OPERATORS = [
  { value: 'eq', label: '等于' },
  { value: 'ne', label: '不等于' },
  { value: 'gt', label: '大于' },
  { value: 'lt', label: '小于' },
  { value: 'ge', label: '大于等于' },
  { value: 'le', label: '小于等于' },
  { value: 'contains', label: '包含' },
  { value: 'regex', label: '正则匹配' },
  { value: 'type', label: '类型是' },
];

export function assertionTypeMeta(type?: string): AssertionTypeMeta {
  return ASSERTION_TYPES.find((t) => t.value === type) || ASSERTION_TYPES[0];
}

/** 新增某类型断言时的默认表达式/操作符/期望值。 */
export function assertionDefaults(type: string) {
  switch (type) {
    case 'json_path':
      return { operator: 'eq', expression: '$.code', expected_text: '200' };
    case 'header':
      return {
        operator: 'contains',
        expression: 'Content-Type',
        expected_text: 'application/json',
      };
    case 'response_time':
      return { operator: 'le', expression: '', expected_text: '1.0' };
    case 'json_schema':
      return {
        operator: 'eq',
        expression: '',
        expected_text: '{\n  "type": "object",\n  "required": ["code"]\n}',
      };
    default:
      return { operator: 'eq', expression: '', expected_text: '200' };
  }
}

/** 后端返回的断言规则 -> 表单值。 */
export function assertionToFormValue(
  rule: {
    assertion_type: string;
    expression?: string | null;
    operator: string;
    expected?: unknown;
    priority?: string;
    order?: number;
  },
  index: number
) {
  return {
    assertion_type: rule.assertion_type,
    expression: rule.expression ?? '',
    operator: rule.operator || 'eq',
    expected_text:
      rule.expected === undefined || rule.expected === null
        ? ''
        : String(rule.expected),
    priority: rule.priority || 'P1',
    order: rule.order ?? index,
  };
}

/** 表单值 -> 提交给后端的断言规则。 */
export function assertionsFromFormValues(
  values: Array<{
    assertion_type?: string;
    expression?: string;
    operator?: string;
    expected_text?: unknown;
    priority?: string;
  }> | undefined
) {
  return (values || []).map((rule, index) => {
    const text =
      rule.expected_text === undefined || rule.expected_text === null
        ? ''
        : String(rule.expected_text).trim();
    return {
      assertion_type: rule.assertion_type || 'status_code',
      expression: rule.expression?.trim() ? rule.expression : null,
      operator: rule.operator || 'eq',
      expected: text === '' ? null : text,
      priority: rule.priority || 'P1',
      order: index,
    };
  });
}

export function defaultStatusCodeAssertion(priority = 'P1') {
  return {
    assertion_type: 'status_code',
    expression: '',
    operator: 'eq',
    expected_text: '200',
    priority,
  };
}
