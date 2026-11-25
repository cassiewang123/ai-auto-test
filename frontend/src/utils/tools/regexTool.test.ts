import { describe, expect, it } from 'vitest';
import { buildHighlightSegments, evaluateRegex } from './regexTool';

describe('buildHighlightSegments 命中高亮片段', () => {
  it('多匹配：命中与未命中片段交替且拼接后与原文一致', () => {
    const text = 'a1b22c333';
    const evaluation = evaluateRegex('\\d+', 'g', text);
    expect(evaluation.matches).toHaveLength(3);

    const segments = buildHighlightSegments(text, evaluation.matches);
    expect(segments).toEqual([
      { text: 'a', matched: false },
      { text: '1', matched: true },
      { text: 'b', matched: false },
      { text: '22', matched: true },
      { text: 'c', matched: false },
      { text: '333', matched: true },
    ]);
    expect(segments.map((segment) => segment.text).join('')).toBe(text);
    expect(segments.filter((segment) => segment.matched)).toHaveLength(3);
  });

  it('零匹配：返回整段未命中片段', () => {
    const evaluation = evaluateRegex('zzz', 'g', 'abc');
    expect(evaluation.matches).toHaveLength(0);

    const segments = buildHighlightSegments('abc', evaluation.matches);
    expect(segments).toEqual([{ text: 'abc', matched: false }]);
  });

  it('非法正则与越界历史数据不会抛错', () => {
    const invalid = evaluateRegex('([', 'g', 'x');
    expect(invalid.valid).toBe(false);
    expect(buildHighlightSegments('x', invalid.matches)).toEqual([
      { text: 'x', matched: false },
    ]);

    // 防御：索引越界的脏数据不应截断或破坏原文
    const defensive = buildHighlightSegments('ab', [
      { index: 5, value: 'xyz', groups: [], namedGroups: {} },
    ]);
    expect(defensive).toEqual([{ text: 'ab', matched: false }]);
  });
});
