import { describe, expect, it } from 'vitest';
import {
  buildGroupSelectOptions,
  buildGroupTree,
  groupDepth,
  groupItemsByPath,
  isUnderGroup,
  normalizeGroupPath,
  parentGroupPath,
} from './apiModules';

describe('normalizeGroupPath', () => {
  it('收紧斜杠与空白', () => {
    expect(normalizeGroupPath(' 磐石关务 // 回执 / ')).toBe('磐石关务/回执');
  });

  it('空值返回空串', () => {
    expect(normalizeGroupPath(null)).toBe('');
    expect(normalizeGroupPath(undefined)).toBe('');
    expect(normalizeGroupPath('  ')).toBe('');
  });
});

describe('parentGroupPath / groupDepth', () => {
  it('拆出父级与层级', () => {
    expect(parentGroupPath('磐石关务/回执/新增')).toBe('磐石关务/回执');
    expect(parentGroupPath('磐石关务')).toBe('');
    expect(groupDepth('磐石关务')).toBe(1);
    expect(groupDepth('磐石关务/回执')).toBe(2);
    expect(groupDepth('')).toBe(0);
  });
});

describe('isUnderGroup', () => {
  it('父模块包含全部子模块', () => {
    expect(isUnderGroup('磐石关务/回执/新增', '磐石关务')).toBe(true);
    expect(isUnderGroup('磐石关务', '磐石关务')).toBe(true);
  });

  it('不会误命中同前缀的兄弟模块', () => {
    expect(isUnderGroup('磐石关务二期', '磐石关务')).toBe(false);
  });

  it('空串表示未分组', () => {
    expect(isUnderGroup(null, '')).toBe(true);
    expect(isUnderGroup('磐石关务', '')).toBe(false);
  });
});

describe('buildGroupTree', () => {
  const items = [
    { title: 'a', group_path: '磐石关务/回执' },
    { title: 'b', group_path: '磐石关务/回执' },
    { title: 'c', group_path: '磐石关务/回执/新增' },
    { title: 'd', group_path: 'swgd-param' },
    { title: 'e', group_path: null },
  ];

  it('补齐父级并累计数量', () => {
    const tree = buildGroupTree(items);
    const root = tree.find((node) => node.path === '磐石关务');
    expect(root).toBeTruthy();
    expect(root?.directCount).toBe(0);
    expect(root?.totalCount).toBe(3);
    expect(root?.children.map((child) => child.path)).toEqual(['磐石关务/回执']);
  });

  it('未分组默认不出现在树里，可按需追加', () => {
    expect(buildGroupTree(items).some((node) => node.path === '')).toBe(false);
    const withUngrouped = buildGroupTree(items, [], { includeUngrouped: true });
    const ungrouped = withUngrouped.find((node) => node.path === '');
    expect(ungrouped?.name).toBe('未分组');
    expect(ungrouped?.totalCount).toBe(1);
  });

  it('空模块也能出现在树里', () => {
    const tree = buildGroupTree([], ['空模块/子模块']);
    expect(tree.map((node) => node.path)).toEqual(['空模块']);
    expect(tree[0].children.map((node) => node.path)).toEqual([
      '空模块/子模块',
    ]);
    expect(tree[0].totalCount).toBe(0);
  });

  it('同级模块按名称排序', () => {
    const tree = buildGroupTree([
      { group_path: 'B 模块' },
      { group_path: 'A 模块' },
    ]);
    expect(tree.map((node) => node.name)).toEqual(['A 模块', 'B 模块']);
  });
});

describe('groupItemsByPath', () => {
  it('按模块分桶，未分组排最后', () => {
    const buckets = groupItemsByPath([
      { title: 'a', group_path: '磐石关务/回执' },
      { title: 'b', group_path: '磐石关务/回执' },
      { title: 'c', group_path: 'swgd-param' },
      { title: 'd', group_path: null },
    ]);
    expect(buckets.map((bucket) => bucket.path)).toEqual([
      'swgd-param',
      '磐石关务/回执',
      '',
    ]);
    expect(buckets[1].items).toHaveLength(2);
  });

  it('规范化斜杠后再分桶', () => {
    const buckets = groupItemsByPath([
      { group_path: 'A/B' },
      { group_path: ' A / B ' },
    ]);
    expect(buckets).toHaveLength(1);
    expect(buckets[0].items).toHaveLength(2);
  });
});

describe('buildGroupSelectOptions', () => {
  it('补齐父级并按层级缩进', () => {
    const options = buildGroupSelectOptions(['磐石关务/回执']);
    expect(options.map((item) => item.value)).toEqual([
      '磐石关务',
      '磐石关务/回执',
    ]);
    expect(options[0].display).toBe('磐石关务');
    expect(options[1].display).toBe('　回执');
  });

  it('可选追加未分组项', () => {
    const options = buildGroupSelectOptions(['A'], { includeEmpty: true });
    const empty = options[options.length - 1];
    expect(empty.value).toBe('');
    expect(empty.label).toBe('未分组');
  });

  it('去重', () => {
    const options = buildGroupSelectOptions(['A', 'A/B', 'A/B']);
    expect(options).toHaveLength(2);
  });
});
