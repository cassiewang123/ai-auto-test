import { describe, expect, it } from 'vitest';
import {
  diffCharsInline,
  diffTextLines,
} from './textDiff';

describe('diffTextLines 对比选项', () => {
  it('缺省选项时与历史行为一致', () => {
    const result = diffTextLines('a\nb\nc', 'a\nx\nc');
    expect(result.added).toBe(1);
    expect(result.removed).toBe(1);
    expect(result.unchanged).toBe(2);
    expect(result.lines.map((line) => line.kind)).toEqual([
      'same',
      'removed',
      'added',
      'same',
    ]);
  });

  it('忽略行尾空白后仅空白差异不再计入差异', () => {
    const strict = diffTextLines('a \nb', 'a\nb');
    expect(strict.removed).toBe(1);
    expect(strict.added).toBe(1);

    const relaxed = diffTextLines('a \nb', 'a\nb', { ignoreTrailingWhitespace: true });
    expect(relaxed.added).toBe(0);
    expect(relaxed.removed).toBe(0);
    expect(relaxed.unchanged).toBe(2);
  });

  it('忽略空行后空行差异消失且保留原文行号', () => {
    const result = diffTextLines('a\n\nb', 'a\nb', { ignoreBlankLines: true });
    expect(result.added).toBe(0);
    expect(result.removed).toBe(0);
    expect(result.unchanged).toBe(2);
    // 第二个相同行来自左侧第 3 行（中间空行被忽略但行号不重排）
    expect(result.lines[1].leftNumber).toBe(3);
    expect(result.lines[1].rightNumber).toBe(2);
  });

  it('忽略大小写后仅大小写差异视为相同，展示仍用原文', () => {
    const result = diffTextLines('ABC', 'abc', { ignoreCase: true });
    expect(result.unchanged).toBe(1);
    expect(result.lines[0].text).toBe('ABC');
  });
});

describe('diffCharsInline 行内字符差异', () => {
  it('完全相同的文本没有差异片段', () => {
    const result = diffCharsInline('orderId: 1001', 'orderId: 1001');
    expect(result.left).toEqual([{ text: 'orderId: 1001', changed: false }]);
    expect(result.right).toEqual([{ text: 'orderId: 1001', changed: false }]);
    expect(result.left.some((segment) => segment.changed)).toBe(false);
  });

  it('不同的文本高亮中间差异字符，前后公共部分保持不变', () => {
    const result = diffCharsInline('orderId: 1001', 'orderId: 1002');
    expect(result.left).toEqual([
      { text: 'orderId: 100', changed: false },
      { text: '1', changed: true },
    ]);
    expect(result.right).toEqual([
      { text: 'orderId: 100', changed: false },
      { text: '2', changed: true },
    ]);
  });

  it('忽略大小写时大小写差异不标记为 changed', () => {
    const strict = diffCharsInline('User Active', 'user active');
    expect(strict.left.some((segment) => segment.changed)).toBe(true);

    const relaxed = diffCharsInline('User Active', 'user active', { ignoreCase: true });
    expect(relaxed.left.every((segment) => !segment.changed)).toBe(true);
    expect(relaxed.right.every((segment) => !segment.changed)).toBe(true);
    // 片段拼接后仍与原文一致
    expect(relaxed.left.map((segment) => segment.text).join('')).toBe('User Active');
    expect(relaxed.right.map((segment) => segment.text).join('')).toBe('user active');
  });

  it('一侧为另一侧前缀时仅多余部分标记为差异', () => {
    const result = diffCharsInline('abc', 'abcdef');
    expect(result.left).toEqual([{ text: 'abc', changed: false }]);
    expect(result.right).toEqual([
      { text: 'abc', changed: false },
      { text: 'def', changed: true },
    ]);
  });
});
