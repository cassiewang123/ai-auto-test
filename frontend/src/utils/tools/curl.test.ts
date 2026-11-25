import { describe, expect, it } from 'vitest';
import {
  parseCurl,
  parseUrlEncodedBody,
  shellQuote,
  toCurl,
  tokenizeCommand,
} from './curl';

describe('curl.toCurl', () => {
  it('GET 无 body 时只输出方法与 URL', () => {
    const output = toCurl({ method: 'GET', url: 'https://api.test/users' });
    expect(output).toBe("curl -X GET 'https://api.test/users'");
  });

  it('POST JSON 带 headers 与 --data-raw', () => {
    const output = toCurl({
      method: 'post',
      url: 'https://api.test/users',
      headers: { 'Content-Type': 'application/json' },
      body: { name: 'Ada', age: 36 },
    });
    expect(output).toBe(
      "curl -X POST 'https://api.test/users' -H 'Content-Type: application/json' --data-raw '{\"name\":\"Ada\",\"age\":36}'"
    );
  });

  it('值内含单引号时按 shell 规则转义', () => {
    const output = toCurl({
      method: 'GET',
      url: 'https://api.test/q',
      headers: { 'X-Trace': "it's ok" },
    });
    expect(output).toContain(`-H 'X-Trace: it'\\''s ok'`);
    // 转义后仍然可以被重新解析回来
    expect(parseCurl(output).headers['X-Trace']).toBe("it's ok");
  });

  it('params 追加到 URL，并保留已有 query', () => {
    expect(
      toCurl({ method: 'GET', url: 'https://a.test/p', params: { page: 1, keyword: 'x y' } })
    ).toBe("curl -X GET 'https://a.test/p?page=1&keyword=x y'");
    expect(
      toCurl({ method: 'GET', url: 'https://a.test/p?x=1', params: { page: 2 } })
    ).toBe("curl -X GET 'https://a.test/p?x=1&page=2'");
  });
});

describe('curl.shellQuote', () => {
  it('无单引号时等同直接包裹', () => {
    expect(shellQuote('abc')).toBe("'abc'");
  });

  it('单引号被替换为结束-转义-重开序列', () => {
    expect(shellQuote("a'b")).toBe("'a'\\''b'");
  });
});

describe('curl.tokenizeCommand', () => {
  it('支持反斜杠续行与混合引号', () => {
    const tokens = tokenizeCommand(
      "curl -X POST \\\n  'https://a.test' -H \"X-A: 1\""
    );
    expect(tokens).toEqual(['curl', '-X', 'POST', 'https://a.test', '-H', 'X-A: 1']);
  });
});

describe('curl.parseCurl', () => {
  it('仅 URL 时推断为 GET', () => {
    const parsed = parseCurl("curl 'https://api.test/users'");
    expect(parsed).toEqual({
      method: 'GET',
      url: 'https://api.test/users',
      headers: {},
    });
    expect(parsed.body).toBeUndefined();
  });

  it('解析 POST JSON，body 自动转成对象', () => {
    const parsed = parseCurl(
      `curl -X POST 'https://api.test/users' -H 'Content-Type: application/json' -d '{"name":"Ada"}'`
    );
    expect(parsed.method).toBe('POST');
    expect(parsed.url).toBe('https://api.test/users');
    expect(parsed.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(parsed.body).toEqual({ name: 'Ada' });
  });

  it('多个 header 全部解析', () => {
    const parsed = parseCurl(
      `curl -H 'Accept: application/json' -H 'X-Token:abc' -H 'Accept-Language: zh-CN' https://api.test/a`
    );
    expect(parsed.headers).toEqual({
      Accept: 'application/json',
      'X-Token': 'abc',
      'Accept-Language': 'zh-CN',
    });
  });

  it('长短选项混用', () => {
    const parsed = parseCurl(
      `curl --request PUT --header 'Content-Type: application/json' --data-raw '{"id":1}' --url 'https://api.test/item/1'`
    );
    expect(parsed.method).toBe('PUT');
    expect(parsed.url).toBe('https://api.test/item/1');
    expect(parsed.body).toEqual({ id: 1 });
  });

  it('urlencoded body 保持字符串且推断 POST', () => {
    const parsed = parseCurl(
      `curl 'https://api.test/login' -H 'Content-Type: application/x-www-form-urlencoded' -d 'user=admin&pass=1'`
    );
    expect(parsed.method).toBe('POST');
    expect(parsed.body).toBe('user=admin&pass=1');
    expect(parseUrlEncodedBody(String(parsed.body))).toEqual({
      user: 'admin',
      pass: '1',
    });
  });

  it('URL 作为位置参数出现在选项之前', () => {
    const parsed = parseCurl(
      `curl https://api.test/orders -X PATCH -H 'X-A: 1' -d '{"qty":2}'`
    );
    expect(parsed.method).toBe('PATCH');
    expect(parsed.url).toBe('https://api.test/orders');
    expect(parsed.body).toEqual({ qty: 2 });
  });

  it('忽略 -k/-L/-s/-v 等布尔 flag', () => {
    const parsed = parseCurl(
      `curl -k -L -s -v --compressed 'https://api.test/insecure'`
    );
    expect(parsed.url).toBe('https://api.test/insecure');
    expect(parsed.method).toBe('GET');
    expect(parsed.headers).toEqual({});
  });

  it('多个 --data 片段按 & 拼接', () => {
    const parsed = parseCurl(
      `curl 'https://api.test/f' -d 'a=1' -d 'b=2'`
    );
    expect(parsed.body).toBe('a=1&b=2');
  });

  it('缺少 URL 时抛出可读错误', () => {
    expect(() => parseCurl('curl -X POST')).toThrow('未能从 cURL 命令中解析出请求 URL');
    expect(() => parseCurl('   ')).toThrow('请输入 cURL 命令');
  });

  it('去掉终端提示符前缀', () => {
    const parsed = parseCurl(`$ curl 'https://api.test/x'`);
    expect(parsed.url).toBe('https://api.test/x');
  });
});

describe('curl 往返一致性', () => {
  it('toCurl → parseCurl 保留方法/URL/headers/body', () => {
    const input = {
      method: 'DELETE',
      url: 'https://api.test/items/9',
      headers: { Authorization: 'Bearer abc', 'X-Note': "o'hara" },
      body: { force: true },
    };
    const parsed = parseCurl(toCurl(input));
    expect(parsed.method).toBe('DELETE');
    expect(parsed.url).toBe('https://api.test/items/9');
    expect(parsed.headers).toEqual(input.headers);
    expect(parsed.body).toEqual({ force: true });
  });
});
