export type JsonExpectedType = 'any' | 'object' | 'array';

export interface JsonValidationResult {
  valid: boolean;
  value?: unknown;
  error?: string;
}

function expectedTypeLabel(expectedType: JsonExpectedType): string {
  if (expectedType === 'object') return 'JSON 对象';
  if (expectedType === 'array') return 'JSON 数组';
  return 'JSON';
}

function matchesExpectedType(value: unknown, expectedType: JsonExpectedType): boolean {
  if (expectedType === 'any') return true;
  if (expectedType === 'array') return Array.isArray(value);
  return Boolean(value) && !Array.isArray(value) && typeof value === 'object';
}

export function validateJsonText(
  text: string | undefined,
  options: {
    allowEmpty?: boolean;
    expectedType?: JsonExpectedType;
  } = {}
): JsonValidationResult {
  const value = text?.trim() ?? '';
  const allowEmpty = options.allowEmpty ?? true;
  const expectedType = options.expectedType ?? 'any';

  if (!value) {
    return allowEmpty
      ? { valid: true, value: undefined }
      : { valid: false, error: '请输入 JSON 内容' };
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (!matchesExpectedType(parsed, expectedType)) {
      return {
        valid: false,
        error: `请输入 ${expectedTypeLabel(expectedType)}`,
      };
    }
    return { valid: true, value: parsed };
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'JSON 解析失败';
    return { valid: false, error: `JSON 格式不正确：${detail}` };
  }
}

export function parseJsonText(
  text: string | undefined,
  label: string,
  options: {
    allowEmpty?: boolean;
    expectedType?: JsonExpectedType;
  } = {}
): unknown {
  const result = validateJsonText(text, options);
  if (!result.valid) {
    throw new Error(`${label}${result.error ? `：${result.error}` : ''}`);
  }
  return result.value;
}

export function formatJson(value: unknown, spacing = 2): string {
  return JSON.stringify(value, null, spacing);
}

export function compactJson(value: unknown): string {
  return JSON.stringify(value);
}

export function jsonFormValidator(
  label: string,
  options: {
    allowEmpty?: boolean;
    expectedType?: JsonExpectedType;
  } = {}
) {
  return async (_: unknown, value: string | undefined): Promise<void> => {
    const result = validateJsonText(value, options);
    if (!result.valid) {
      throw new Error(`${label}${result.error ? `：${result.error}` : ''}`);
    }
  };
}
