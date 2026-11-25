import { describe, expect, it } from 'vitest';
import {
  byteLength,
  formatByteSize,
  formatRelativeTime,
  getResponseHeader,
  parseResponseCookies,
  parseSetCookie,
  renderResponseBody,
  splitCombinedSetCookie,
} from './httpResponse';

describe('httpResponse.getResponseHeader', () => {
  it('大小写不敏感取值', () => {
    expect(getResponseHeader({ 'content-type': 'application/json' }, 'Content-Type'))
      .toBe('application/json');
  });

  it('缺失时返回 undefined', () => {
    expect(getResponseHeader({}, 'x-missing')).toBeUndefined();
    expect(getResponseHeader(null, 'x-missing')).toBeUndefined();
  });

  it('数组值按逗号拼接', () => {
    expect(getResponseHeader({ 'set-cookie': ['a=1', 'b=2'] }, 'Set-Cookie'))
      .toBe('a=1, b=2');
  });
});

describe('httpResponse.splitCombinedSetCookie', () => {
  it('Expires 中的逗号不会被误拆', () => {
    const combined =
      'sid=abc; Path=/; Expires=Wed, 21 Oct 2037 07:28:00 GMT, theme=dark; Path=/ui';
    expect(splitCombinedSetCookie(combined)).toEqual([
      'sid=abc; Path=/; Expires=Wed, 21 Oct 2037 07:28:00 GMT',
      'theme=dark; Path=/ui',
    ]);
  });
});

describe('httpResponse.parseSetCookie', () => {
  it('解析名称/值/属性', () => {
    const cookie = parseSetCookie(
      'sid=abc123; Domain=.example.com; Path=/api; Expires=Wed, 21 Oct 2037 07:28:00 GMT; HttpOnly; Secure; SameSite=Lax'
    );
    expect(cookie).toEqual({
      name: 'sid',
      value: 'abc123',
      domain: '.example.com',
      path: '/api',
      expires: 'Wed, 21 Oct 2037 07:28:00 GMT',
      httpOnly: true,
      secure: true,
      sameSite: 'Lax',
      raw: 'sid=abc123; Domain=.example.com; Path=/api; Expires=Wed, 21 Oct 2037 07:28:00 GMT; HttpOnly; Secure; SameSite=Lax',
    });
  });

  it('空值或非法内容返回 null', () => {
    expect(parseSetCookie('')).toBeNull();
    expect(parseSetCookie('novalue')).toBeNull();
    expect(parseSetCookie('=abc')).toBeNull();
  });
});

describe('httpResponse.parseResponseCookies', () => {
  it('从响应头解析多条 Cookie', () => {
    const cookies = parseResponseCookies({
      'Set-Cookie': ['sid=1; Path=/', 'theme=dark; Path=/ui'],
    });
    expect(cookies.map((item) => item.name)).toEqual(['sid', 'theme']);
    expect(cookies[0].path).toBe('/');
  });

  it('没有 set-cookie 时返回空数组', () => {
    expect(parseResponseCookies({ 'content-type': 'text/plain' })).toEqual([]);
  });
});

describe('httpResponse.formatByteSize', () => {
  it('按 B / KB / MB 分档', () => {
    expect(formatByteSize(0)).toBe('0 B');
    expect(formatByteSize(512)).toBe('512 B');
    expect(formatByteSize(1024)).toBe('1 KB');
    expect(formatByteSize(1229)).toBe('1.2 KB');
    expect(formatByteSize(1024 * 1024 * 2.5)).toBe('2.5 MB');
  });

  it('byteLength 按 UTF-8 计算', () => {
    expect(byteLength('abc')).toBe(3);
    expect(byteLength('中文')).toBe(6);
    expect(byteLength('')).toBe(0);
  });
});

describe('httpResponse.formatRelativeTime', () => {
  const now = new Date('2024-05-01T12:00:00Z').getTime();

  it('分档展示相对时间', () => {
    expect(formatRelativeTime('2024-05-01T11:59:30Z', now)).toBe('刚刚');
    expect(formatRelativeTime('2024-05-01T11:55:00Z', now)).toBe('5 分钟前');
    expect(formatRelativeTime('2024-05-01T09:00:00Z', now)).toBe('3 小时前');
    expect(formatRelativeTime('2024-04-29T12:00:00Z', now)).toBe('2 天前');
    expect(formatRelativeTime('2024-01-01T12:00:00Z', now)).toBe('2024-01-01');
  });

  it('空值返回占位符', () => {
    expect(formatRelativeTime(null, now)).toBe('-');
    expect(formatRelativeTime(undefined, now)).toBe('-');
  });
});

describe('httpResponse.renderResponseBody', () => {
  it('对象美化输出，字符串原样返回', () => {
    expect(renderResponseBody({ a: 1 })).toBe('{\n  "a": 1\n}');
    expect(renderResponseBody('plain')).toBe('plain');
    expect(renderResponseBody(null, 'raw text')).toBe('raw text');
    expect(renderResponseBody(null)).toBe('');
  });
});
