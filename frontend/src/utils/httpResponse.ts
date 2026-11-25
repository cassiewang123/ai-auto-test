/**
 * 响应展示相关的小工具：响应头查询、Set-Cookie 解析、体积与相对时间格式化。
 *
 * 这些函数只做纯计算，便于在多个组件（响应面板、历史面板）之间复用与单测。
 */

/** 解析后的单条 Cookie */
export interface ParsedResponseCookie {
  name: string;
  value: string;
  domain?: string;
  path?: string;
  expires?: string;
  maxAge?: string;
  sameSite?: string;
  httpOnly?: boolean;
  secure?: boolean;
  /** 原始 Set-Cookie 片段，便于排查 */
  raw: string;
}

type HeaderBag = Record<string, unknown> | null | undefined;

function headerEntries(headers: HeaderBag): Array<[string, unknown]> {
  if (!headers || typeof headers !== 'object') return [];
  return Object.entries(headers);
}

/**
 * 大小写不敏感地取响应头。同名多值会合并为数组返回（如 set-cookie）。
 */
export function collectResponseHeaderValues(
  headers: HeaderBag,
  name: string
): string[] {
  const target = name.trim().toLowerCase();
  const values: string[] = [];
  headerEntries(headers).forEach(([key, value]) => {
    if (key.trim().toLowerCase() !== target) return;
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== null && item !== undefined) values.push(String(item));
      });
      return;
    }
    if (value !== null && value !== undefined) values.push(String(value));
  });
  return values;
}

/** 大小写不敏感地取单个响应头（多值以逗号拼接）。 */
export function getResponseHeader(
  headers: HeaderBag,
  name: string
): string | undefined {
  const values = collectResponseHeaderValues(headers, name);
  return values.length > 0 ? values.join(', ') : undefined;
}

/**
 * 拆分可能被合并成一行的 Set-Cookie。
 *
 * `Expires=Wed, 21 Oct 2015 07:28:00 GMT` 里的逗号后面不是 `name=`，
 * 因此不会被误拆。
 */
export function splitCombinedSetCookie(text: string): string[] {
  const chunks: string[] = [];
  let buffer = '';
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === ',') {
      const rest = text.slice(index + 1);
      if (/^\s*[^;,=\s]+=/.test(rest)) {
        chunks.push(buffer);
        buffer = '';
        continue;
      }
    }
    buffer += char;
  }
  if (buffer.trim()) chunks.push(buffer);
  return chunks.map((chunk) => chunk.trim()).filter(Boolean);
}

/** 解析单条 Set-Cookie 文本 */
export function parseSetCookie(text: string): ParsedResponseCookie | null {
  const trimmed = String(text ?? '').trim();
  if (!trimmed) return null;
  const segments = trimmed
    .split(';')
    .map((segment) => segment.trim())
    .filter(Boolean);
  if (segments.length === 0) return null;

  const first = segments[0];
  const separator = first.indexOf('=');
  if (separator <= 0) return null;

  const cookie: ParsedResponseCookie = {
    name: first.slice(0, separator).trim(),
    value: first.slice(separator + 1).trim(),
    raw: trimmed,
  };
  if (!cookie.name) return null;

  segments.slice(1).forEach((segment) => {
    const attributeSeparator = segment.indexOf('=');
    const attributeName = (
      attributeSeparator === -1 ? segment : segment.slice(0, attributeSeparator)
    )
      .trim()
      .toLowerCase();
    const attributeValue =
      attributeSeparator === -1 ? '' : segment.slice(attributeSeparator + 1).trim();
    switch (attributeName) {
      case 'domain':
        cookie.domain = attributeValue;
        break;
      case 'path':
        cookie.path = attributeValue;
        break;
      case 'expires':
        cookie.expires = attributeValue;
        break;
      case 'max-age':
        cookie.maxAge = attributeValue;
        break;
      case 'samesite':
        cookie.sameSite = attributeValue;
        break;
      case 'httponly':
        cookie.httpOnly = true;
        break;
      case 'secure':
        cookie.secure = true;
        break;
      default:
        break;
    }
  });

  return cookie;
}

/** 从响应头里解析出全部 Cookie（支持 set-cookie 为数组或多行合并的情况） */
export function parseResponseCookies(headers: HeaderBag): ParsedResponseCookie[] {
  const rawValues = collectResponseHeaderValues(headers, 'set-cookie');
  const cookies: ParsedResponseCookie[] = [];
  rawValues.forEach((rawValue) => {
    splitCombinedSetCookie(rawValue).forEach((chunk) => {
      const parsed = parseSetCookie(chunk);
      if (parsed) cookies.push(parsed);
    });
  });
  return cookies;
}

/** 文本的 UTF-8 字节数 */
export function byteLength(text: string): number {
  const value = String(text ?? '');
  if (!value) return 0;
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(value).length;
  }
  return value.length;
}

/** 把字节数格式化成 `1.2 KB` 这类可读文本 */
export function formatByteSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb >= 100 ? Math.round(kb) : Number(kb.toFixed(1))} KB`;
  }
  const mb = kb / 1024;
  return `${mb >= 100 ? Math.round(mb) : Number(mb.toFixed(1))} MB`;
}

/** 相对时间：刚刚 / 5 分钟前 / 3 小时前 / 2 天前 / 日期 */
export function formatRelativeTime(
  iso: string | null | undefined,
  now: number = Date.now()
): string {
  if (!iso) return '-';
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) return iso;

  const diffSeconds = Math.floor((now - timestamp) / 1000);
  if (diffSeconds < 0) {
    // 时钟偏差导致的“未来时间”按刚刚处理
    return '刚刚';
  }
  if (diffSeconds < 60) return '刚刚';
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} 天前`;
  return iso.slice(0, 10);
}

/** 把响应 body 渲染成文本（对象走 JSON.stringify） */
export function renderResponseBody(body: unknown, text?: string | null): string {
  if (body === null || body === undefined) {
    return text && text.length > 0 ? text : '';
  }
  if (typeof body === 'string') return body;
  try {
    return JSON.stringify(body, null, 2) ?? '';
  } catch {
    return text ?? '';
  }
}
