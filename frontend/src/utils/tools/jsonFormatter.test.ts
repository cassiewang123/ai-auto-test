import { describe, expect, it } from 'vitest';
import {
  analyzeJson,
  escapeNonAscii,
  formatJson,
  normalizeJsonError,
} from './jsonFormatter';

const sample = '{"b":1,"a":{"c":[1,2],"d":{"e":"中文"}}}';

describe('jsonFormatter.formatJson', () => {
  it('美化输出使用指定缩进', () => {
    expect(formatJson('{"a":1,"b":[1,2]}', { indent: 2, sortKeys: false, escapeUnicode: false }))
      .toBe(['{', '  "a": 1,', '  "b": [', '    1,', '    2', '  ]', '}'].join('\n'));
  });

  it('indent 为 0 时压缩成一行', () => {
    expect(formatJson(sample, { indent: 0, sortKeys: false, escapeUnicode: false })).toBe(
      '{"b":1,"a":{"c":[1,2],"d":{"e":"中文"}}}'
    );
  });

  it('按 key 排序时逐层生效', () => {
    const output = formatJson(sample, { indent: 2, sortKeys: true, escapeUnicode: false });
    expect(output.indexOf('"a"')).toBeLessThan(output.indexOf('"b"'));
    expect(output.indexOf('"c"')).toBeLessThan(output.indexOf('"d"'));
  });

  it('可以把中文转成 Unicode 转义并保持可解析', () => {
    const output = formatJson('{"name":"中文"}', {
      indent: 0,
      sortKeys: false,
      escapeUnicode: true,
    });
    expect(output).toBe('{"name":"\\u4e2d\\u6587"}');
    expect(JSON.parse(output)).toEqual({ name: '中文' });
  });

  it('非法 JSON 抛出带位置提示的中文错误', () => {
    expect(() => formatJson('{"a":1,}', { indent: 2, sortKeys: false, escapeUnicode: false }))
      .toThrowError(/双引号|语法|分隔符/);
    expect(() => formatJson('', { indent: 2, sortKeys: false, escapeUnicode: false }))
      .toThrowError('请输入 JSON 内容');
  });

  it('空对象与空数组保持紧凑', () => {
    expect(formatJson('{"a":[],"b":{}}', { indent: 2, sortKeys: false, escapeUnicode: false }))
      .toBe(['{', '  "a": [],', '  "b": {}', '}'].join('\n'));
  });
});

describe('jsonFormatter.analyzeJson', () => {
  it('统计字段数、数组元素、层级与字节数', () => {
    const stats = analyzeJson(sample);
    expect(stats.rootType).toBe('object');
    expect(stats.keys).toBe(5);
    expect(stats.items).toBe(2);
    expect(stats.maxDepth).toBe(4);
    expect(stats.bytes).toBeGreaterThan(0);
  });

  it('识别数组根节点', () => {
    expect(analyzeJson('[1,2,3]').rootType).toBe('array');
    expect(analyzeJson('"x"').rootType).toBe('string');
    expect(analyzeJson('null').rootType).toBe('null');
  });
});

describe('jsonFormatter.escapeNonAscii', () => {
  it('只转义非 ASCII 字符', () => {
    expect(escapeNonAscii('a中')).toBe('a\\u4e2d');
  });
});

describe('jsonFormatter.normalizeJsonError', () => {
  it('把英文报错翻译为中文提示', () => {
    const message = normalizeJsonError(new SyntaxError('Unexpected token } in JSON at position 7'));
    expect(message).toContain('多余的符号或缺少分隔符');
    expect(message).toContain('第 8 个字符');
  });

  it('对未知错误给出兜底提示', () => {
    expect(normalizeJsonError(new Error('something odd'))).toBe('JSON 语法不正确');
  });
});
