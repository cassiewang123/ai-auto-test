export interface JsonFormatOptions {
  /** 缩进空格数；0 表示压缩成一行 */
  indent: number;
  /** 是否按 key 排序 */
  sortKeys: boolean;
  /** 是否把非 ASCII 字符转成 \\uXXXX */
  escapeUnicode: boolean;
}

export interface JsonStats {
  rootType: 'object' | 'array' | 'string' | 'number' | 'boolean' | 'null';
  keys: number;
  items: number;
  maxDepth: number;
  bytes: number;
}

export const defaultJsonFormatOptions: JsonFormatOptions = {
  indent: 2,
  sortKeys: false,
  escapeUnicode: false,
};

export function escapeNonAscii(text: string): string {
  return text.replace(/[\u007f-\uffff]/g, (char) => {
    const hex = char.charCodeAt(0).toString(16).padStart(4, '0');
    return `\\u${hex}`;
  });
}

function serialize(
  value: unknown,
  options: JsonFormatOptions,
  pretty: boolean,
  level: number
): string {
  if (value === null) return 'null';

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    const items = value.map((item) => serialize(item, options, pretty, level + 1));
    if (!pretty) return `[${items.join(',')}]`;
    const pad = ' '.repeat(options.indent * (level + 1));
    const closePad = ' '.repeat(options.indent * level);
    return `[\n${pad}${items.join(`,\n${pad}`)}\n${closePad}]`;
  }

  switch (typeof value) {
    case 'object': {
      const source = value as Record<string, unknown>;
      const keys = Object.keys(source).filter((key) => source[key] !== undefined);
      if (options.sortKeys) keys.sort((left, right) => left.localeCompare(right));
      if (keys.length === 0) return '{}';
      const entries = keys.map((key) => {
        const renderedKey = JSON.stringify(key);
        const renderedValue = serialize(source[key], options, pretty, level + 1);
        return pretty ? `${renderedKey}: ${renderedValue}` : `${renderedKey}:${renderedValue}`;
      });
      if (!pretty) return `{${entries.join(',')}}`;
      const pad = ' '.repeat(options.indent * (level + 1));
      const closePad = ' '.repeat(options.indent * level);
      return `{\n${pad}${entries.join(`,\n${pad}`)}\n${closePad}}`;
    }
    case 'string':
      return JSON.stringify(value);
    case 'number':
      return Number.isFinite(value) ? String(value) : 'null';
    case 'boolean':
      return value ? 'true' : 'false';
    default:
      // undefined / function / symbol 在 JSON 中不合法，统一按 null 处理
      return 'null';
  }
}

/** 格式化 JSON 文本：indent 为 0 时输出压缩结果；输入非法时抛出带定位信息的错误 */
export function formatJson(
  text: string,
  options: JsonFormatOptions = defaultJsonFormatOptions
): string {
  if (text.trim() === '') throw new Error('请输入 JSON 内容');
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(normalizeJsonError(error));
  }
  const result = serialize(parsed, options, options.indent > 0, 0);
  return options.escapeUnicode ? escapeNonAscii(result) : result;
}

/** 把 JSON.parse 的英文报错翻译成可读的中文提示，并保留出错位置 */
export function normalizeJsonError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const position = /position (\d+)/.exec(raw);
  const lineColumn = /line (\d+) column (\d+)/.exec(raw);
  const where = lineColumn
    ? `第 ${lineColumn[1]} 行第 ${lineColumn[2]} 列`
    : position
      ? `第 ${Number(position[1]) + 1} 个字符`
      : '';

  const detailMap: Array<[RegExp, string]> = [
    [/Unexpected end of JSON input/, 'JSON 内容不完整，可能缺少收尾的 } 或 ]'],
    [/Unexpected token/, '存在多余的符号或缺少分隔符（逗号、引号、冒号）'],
    [/Unexpected non-whitespace character after JSON/, 'JSON 结束后还有多余内容'],
    [/Bad control character/, '字符串中存在未转义的控制字符'],
    [/Unterminated string/, '字符串没有正确闭合'],
    [/Expected double-quoted property name/, '对象的属性名必须使用双引号'],
    [/Expected property name or '}'/, '对象属性名格式不正确，必须使用双引号'],
  ];
  const matched = detailMap.find(([pattern]) => pattern.test(raw));
  const detail = matched ? matched[1] : 'JSON 语法不正确';
  return where ? `${detail}（${where}）` : detail;
}

export function analyzeJson(text: string): JsonStats {
  const value: unknown = JSON.parse(text);
  let keys = 0;
  let items = 0;
  let maxDepth = 0;

  function walk(node: unknown, depth: number) {
    maxDepth = Math.max(maxDepth, depth);
    if (Array.isArray(node)) {
      items += node.length;
      node.forEach((item) => walk(item, depth + 1));
      return;
    }
    if (node && typeof node === 'object') {
      const entries = Object.entries(node as Record<string, unknown>);
      keys += entries.length;
      entries.forEach(([, item]) => walk(item, depth + 1));
    }
  }

  walk(value, 1);

  const rootType: JsonStats['rootType'] =
    value === null
      ? 'null'
      : Array.isArray(value)
        ? 'array'
        : (typeof value as JsonStats['rootType']);

  return {
    rootType,
    keys,
    items,
    maxDepth,
    bytes: new TextEncoder().encode(text).length,
  };
}
