import { describe, expect, it } from 'vitest';
import { matchesGroupPath, splitGroupPath } from './groupPath';

describe('matchesGroupPath', () => {
  it('命中分组本身', () => {
    expect(matchesGroupPath('swgd-imap-content', 'swgd-imap-content')).toBe(true);
  });

  it('命中所有子分组（父级模块不应显示 0 个接口）', () => {
    expect(
      matchesGroupPath('swgd-imap-content/ApiType 码表', 'swgd-imap-content')
    ).toBe(true);
    expect(
      matchesGroupPath(
        'swgd-imap-content/ApiService 接口调试/在线文档',
        'swgd-imap-content'
      )
    ).toBe(true);
  });

  it('不会误命中同前缀的其他分组', () => {
    expect(matchesGroupPath('swgd-imap-enterprise', 'swgd-imap-content')).toBe(
      false
    );
    // "swgd-imap-content-x" 不属于 "swgd-imap-content"
    expect(matchesGroupPath('swgd-imap-content-x', 'swgd-imap-content')).toBe(
      false
    );
  });

  it('选择子分组时不包含父级接口', () => {
    expect(
      matchesGroupPath('swgd-imap-content', 'swgd-imap-content/ApiType 码表')
    ).toBe(false);
  });

  it('空分组表示未分组', () => {
    expect(matchesGroupPath('', '')).toBe(true);
    expect(matchesGroupPath(null, '')).toBe(true);
    expect(matchesGroupPath('任意分组', '')).toBe(false);
  });

  it('忽略首尾空白', () => {
    expect(matchesGroupPath(' 分组A/子 ', '分组A')).toBe(true);
  });
});

describe('splitGroupPath', () => {
  it('拆出叶子与父级路径', () => {
    expect(splitGroupPath('swgd-imap-content/ApiType 码表')).toEqual({
      leaf: 'ApiType 码表',
      prefix: 'swgd-imap-content',
    });
  });

  it('顶级分组没有父级', () => {
    expect(splitGroupPath('磐石关务')).toEqual({ leaf: '磐石关务', prefix: '' });
  });

  it('空路径返回空结果', () => {
    expect(splitGroupPath('')).toEqual({ leaf: '', prefix: '' });
  });
});
