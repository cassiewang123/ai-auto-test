/**
 * cURL 与请求表单互转工具。
 *
 * - `toCurl`：把当前请求配置渲染成可直接在终端执行的 cURL 命令。
 * - `parseCurl`：把粘贴的 cURL 命令解析回 { method, url, headers, body }。
 *
 * 只处理最常见的单条请求场景（本机单人调试），不追求覆盖 cURL 全量参数。
 */

/** 待转换的请求配置（与接口调试页表单字段对齐） */
export interface CurlRequestInput {
  method?: string;
  url?: string;
  headers?: Record<string, string>;
  /** query 参数会按 `k=v` 追加到 URL 上 */
  params?: Record<string, unknown>;
  body?: unknown;
}

/** cURL 解析结果 */
export interface ParsedCurl {
  method: string;
  url: string;
  headers: Record<string, string>;
  body?: unknown;
}

/** 需要读取下一个 token 作为值的长/短选项（用于跳过未知选项时不吃掉 URL） */
const VALUE_OPTIONS = new Set<string>([
  '-X',
  '--request',
  '-H',
  '--header',
  '-d',
  '--data',
  '--data-raw',
  '--data-binary',
  '--data-ascii',
  '--data-urlencode',
  '--url',
  '-u',
  '--user',
  '-F',
  '--form',
  '-b',
  '--cookie',
  '-A',
  '--user-agent',
  '-e',
  '--referer',
  '-o',
  '--output',
  '-m',
  '--max-time',
  '--connect-timeout',
  '-T',
  '--upload-file',
  '-w',
  '--write-out',
  '--retry',
  '--cacert',
  '--cert',
  '--key',
  '--resolve',
  '--proxy',
  '-x',
]);

/** 无值布尔选项：解析时直接忽略 */
const BOOLEAN_OPTIONS = new Set<string>([
  '-k',
  '--insecure',
  '-L',
  '--location',
  '-s',
  '--silent',
  '-v',
  '--verbose',
  '-i',
  '--include',
  '-S',
  '--show-error',
  '-g',
  '--globoff',
  '--compressed',
  '--no-buffer',
  '-N',
  '--http1.1',
  '--http2',
  '--fail',
  '-f',
]);

/** 判定 body 数据来源的选项 */
const BODY_OPTIONS = new Set<string>([
  '-d',
  '--data',
  '--data-raw',
  '--data-binary',
  '--data-ascii',
  '--data-urlencode',
]);

/**
 * 按 POSIX shell 规则对值加单引号。
 *
 * 单引号内部不能再出现单引号，因此把 `'` 转义为 `'\''`（结束-转义-重新开始）。
 */
export function shellQuote(value: string): string {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

/** 把对象值渲染成 query string 片段里的字符串 */
function stringifyParamValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** 把 params 追加到 url（保留已有 query） */
export function appendQueryParams(
  url: string,
  params?: Record<string, unknown>
): string {
  const entries = Object.entries(params ?? {}).filter(([key]) => key.trim());
  if (entries.length === 0) return url;
  const query = entries
    .map(([key, value]) => `${key}=${stringifyParamValue(value)}`)
    .join('&');
  if (!url) return `?${query}`;
  if (!url.includes('?')) return `${url}?${query}`;
  return url.endsWith('?') || url.endsWith('&') ? `${url}${query}` : `${url}&${query}`;
}

/**
 * 把请求配置转换成 cURL 命令。
 *
 * 输出形如：`curl -X POST 'https://a.b' -H 'k: v' --data-raw '{"a":1}'`
 */
export function toCurl(input: CurlRequestInput): string {
  const method = (input.method || 'GET').trim().toUpperCase() || 'GET';
  const url = appendQueryParams(input.url ?? '', input.params);
  const parts: string[] = ['curl', '-X', method, shellQuote(url)];

  Object.entries(input.headers ?? {}).forEach(([key, value]) => {
    const headerName = key.trim();
    if (!headerName) return;
    parts.push('-H', shellQuote(`${headerName}: ${value ?? ''}`));
  });

  if (input.body !== undefined && input.body !== null) {
    const bodyText =
      typeof input.body === 'string' ? input.body : JSON.stringify(input.body);
    if (bodyText) {
      parts.push('--data-raw', shellQuote(bodyText));
    }
  }

  return parts.join(' ');
}

/**
 * 把命令文本拆成 token，支持单/双引号、反斜杠续行与 shell 转义。
 */
export function tokenizeCommand(text: string): string[] {
  const tokens: string[] = [];
  let current = '';
  let started = false;
  let quote: '"' | "'" | null = null;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (quote) {
      if (char === quote) {
        quote = null;
        continue;
      }
      if (quote === '"' && char === '\\' && index + 1 < text.length) {
        index += 1;
        const escaped = text[index];
        current += escaped === 'n' ? '\n' : escaped === 't' ? '\t' : escaped;
        started = true;
        continue;
      }
      current += char;
      continue;
    }

    if (char === '"' || char === "'") {
      quote = char;
      started = true;
      continue;
    }

    if (char === '\\' && index + 1 < text.length) {
      const next = text[index + 1];
      // 行尾反斜杠：续行
      if (next === '\n') {
        index += 1;
        continue;
      }
      if (next === '\r') {
        index += 1;
        if (text[index + 1] === '\n') index += 1;
        continue;
      }
      index += 1;
      current += text[index];
      started = true;
      continue;
    }

    if (/\s/.test(char)) {
      if (started || current) {
        tokens.push(current);
        current = '';
        started = false;
      }
      continue;
    }

    current += char;
    started = true;
  }

  if (started || current) tokens.push(current);
  return tokens;
}

/** body 文本尽量解析为 JSON，失败则原样返回字符串 */
function parseBodyText(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return text;
  }
}

/**
 * 解析 cURL 命令。
 *
 * 支持：`-X/--request`、`-H/--header`、`-d/--data/--data-raw/--data-binary/
 * --data-ascii/--data-urlencode`、`--url`、位置参数 URL。
 * 未知 flag（如 `-k/-L/-s/-v`）会被忽略。
 *
 * @throws 当命令中解析不到 URL 时抛出可读错误
 */
export function parseCurl(text: string): ParsedCurl {
  const source = String(text ?? '')
    .replace(/^\s*[$>]\s+/, '') // 去掉终端提示符
    .trim();
  if (!source) {
    throw new Error('请输入 cURL 命令');
  }

  const tokens = tokenizeCommand(source);
  if (tokens.length === 0) {
    throw new Error('请输入 cURL 命令');
  }

  // 第一个 token 允许是 curl/wget 之类的可执行名
  const startIndex = tokens[0].toLowerCase().startsWith('curl') ? 1 : 0;

  const headers: Record<string, string> = {};
  const bodyChunks: string[] = [];
  let method = '';
  let url = '';

  for (let index = startIndex; index < tokens.length; index += 1) {
    const token = tokens[index];

    if (token === '-X' || token === '--request') {
      method = (tokens[index + 1] ?? '').trim().toUpperCase();
      index += 1;
      continue;
    }

    if (token === '-H' || token === '--header') {
      const raw = tokens[index + 1] ?? '';
      index += 1;
      const separator = raw.indexOf(':');
      if (separator > 0) {
        const key = raw.slice(0, separator).trim();
        const value = raw.slice(separator + 1).trim();
        if (key) headers[key] = value;
      }
      continue;
    }

    if (BODY_OPTIONS.has(token)) {
      bodyChunks.push(tokens[index + 1] ?? '');
      index += 1;
      continue;
    }

    if (token === '--url') {
      url = (tokens[index + 1] ?? '').trim();
      index += 1;
      continue;
    }

    if (BOOLEAN_OPTIONS.has(token)) {
      continue;
    }

    if (VALUE_OPTIONS.has(token)) {
      // 已知但当前不参与组装的选项：跳过它的值
      index += 1;
      continue;
    }

    if (token.startsWith('-')) {
      // 未知 flag：忽略（若它恰好带值，值会在下一轮被当作 URL 候选，
      // 但只有在 url 为空且形如 URL 时才会采用）
      continue;
    }

    if (!url) {
      url = token.trim();
      continue;
    }

    // 多余的裸参数忽略
  }

  if (!url) {
    throw new Error('未能从 cURL 命令中解析出请求 URL');
  }

  const bodyText = bodyChunks.join('&');
  const body = bodyChunks.length > 0 ? parseBodyText(bodyText) : undefined;
  const resolvedMethod =
    method || (body !== undefined ? 'POST' : 'GET');

  const result: ParsedCurl = {
    method: resolvedMethod,
    url,
    headers,
  };
  if (body !== undefined) {
    result.body = body;
  }
  return result;
}

/**
 * 判断 body 文本是否像 `a=1&b=2` 的 urlencoded 形式，并解析成对象。
 */
export function parseUrlEncodedBody(
  text: string
): Record<string, string> | null {
  const trimmed = String(text ?? '').trim();
  if (!trimmed || trimmed.startsWith('{') || trimmed.startsWith('[')) return null;
  if (!trimmed.includes('=')) return null;
  const result: Record<string, string> = {};
  trimmed.split('&').forEach((pair) => {
    if (!pair) return;
    const separator = pair.indexOf('=');
    const rawKey = separator === -1 ? pair : pair.slice(0, separator);
    const rawValue = separator === -1 ? '' : pair.slice(separator + 1);
    if (!rawKey) return;
    result[decodeURIComponentSafe(rawKey)] = decodeURIComponentSafe(rawValue);
  });
  return Object.keys(result).length > 0 ? result : null;
}

function decodeURIComponentSafe(value: string): string {
  const normalized = value.replace(/\+/g, ' ');
  try {
    return decodeURIComponent(normalized);
  } catch {
    return normalized;
  }
}
