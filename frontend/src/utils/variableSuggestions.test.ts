import { describe, expect, it } from 'vitest';
import {
  buildVariableSuggestions,
  matchOpenVariablePlaceholder,
} from './variableSuggestions';

describe('variableSuggestions.matchOpenVariablePlaceholder', () => {
  it('识别末尾未闭合的占位符', () => {
    expect(matchOpenVariablePlaceholder('https://a.test/{{')).toBe('');
    expect(matchOpenVariablePlaceholder('https://a.test/{{ba')).toBe('ba');
    expect(matchOpenVariablePlaceholder('{{a}} and {{to')).toBe('to');
  });

  it('已闭合或没有占位符时返回 null', () => {
    expect(matchOpenVariablePlaceholder('https://a.test')).toBeNull();
    expect(matchOpenVariablePlaceholder('{{base_url}}/users')).toBeNull();
    expect(matchOpenVariablePlaceholder('')).toBeNull();
  });
});

describe('variableSuggestions.buildVariableSuggestions', () => {
  const names = ['base_url', 'token', 'user_id'];

  it('无 {{ 前缀时不给候选', () => {
    expect(buildVariableSuggestions('https://a.test', names)).toEqual([]);
  });

  it('输入 {{ 时给出全部候选（按名称排序）', () => {
    const suggestions = buildVariableSuggestions('https://a.test/{{', names);
    expect(suggestions.map((item) => item.label)).toEqual([
      'base_url',
      'token',
      'user_id',
    ]);
  });

  it('按已输入片段过滤（大小写不敏感）', () => {
    const suggestions = buildVariableSuggestions('{{TO', names);
    expect(suggestions.map((item) => item.label)).toEqual(['token']);
    expect(suggestions[0].value).toBe('{{token}}');
  });

  it('补全只替换末尾的未闭合片段，保留前面的内容', () => {
    expect(
      buildVariableSuggestions('https://a.test/{{base}}/x?{{', ['token'])[0].value
    ).toBe('https://a.test/{{base}}/x?{{token}}');
  });

  it('已闭合的占位符不再触发提示', () => {
    expect(buildVariableSuggestions('{{token}}', names)).toEqual([]);
  });
});
