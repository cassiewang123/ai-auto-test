/**
 * 模块（分组）工具：把 `group_path` 组织成前端可直接使用的结构与选项。
 *
 * 接口用例、接口管理、生成页都以 `group_path` 表达层级（`A/B/C`），
 * 页面需要三件事：
 *   1. 按模块把用例分桶（用例管理按模块显示）；
 *   2. 把接口按模块分桶（生成页按模块批量生成）；
 *   3. 生成「层级缩进的模块下拉选项」，让父子模块在选择器里可区分。
 * 这三件事此前分散在各页面里各写一遍，容易在「父级模块是否含子模块」
 * 这类语义上不一致，因此收敛到这里。
 */

/** 把分组路径规范化：去空白、去首尾/重复斜杠 */
export function normalizeGroupPath(path: string | null | undefined): string {
  return (path || '')
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean)
    .join('/');
}

/** 父级路径；顶级模块返回空串 */
export function parentGroupPath(path: string | null | undefined): string {
  const normalized = normalizeGroupPath(path);
  const index = normalized.lastIndexOf('/');
  return index < 0 ? '' : normalized.slice(0, index);
}

/** 模块层级深度，顶级模块为 1；未分组为 0 */
export function groupDepth(path: string | null | undefined): number {
  const normalized = normalizeGroupPath(path);
  return normalized ? normalized.split('/').length : 0;
}

/** 判断用例是否属于所选模块（含其下所有子模块） */
export function isUnderGroup(
  caseGroupPath: string | null | undefined,
  selectedGroupPath: string | null | undefined
): boolean {
  const current = normalizeGroupPath(caseGroupPath);
  const selected = normalizeGroupPath(selectedGroupPath);
  if (!selected) return current === '';
  return current === selected || current.startsWith(`${selected}/`);
}

export interface GroupTreeItem {
  /** 完整分组路径；未分组为空串 */
  path: string;
  /** 模块名（路径叶子） */
  name: string;
  parentPath: string;
  depth: number;
  /** 本模块直属的用例/接口数 */
  directCount: number;
  /** 含子模块的累计数量 */
  totalCount: number;
  children: GroupTreeItem[];
}

type CountableItem = { group_path?: string | null };

/**
 * 按模块把条目组织成树。
 *
 * @param items 带 `group_path` 的条目
 * @param extraPaths 额外需要展示的模块路径（例如空模块），会补齐其所有父级
 * @param options.includeUngrouped 是否把「未分组」作为树节点返回
 */
export function buildGroupTree<T extends CountableItem>(
  items: readonly T[],
  extraPaths: readonly string[] = [],
  options: { includeUngrouped?: boolean } = {}
): GroupTreeItem[] {
  const nodes = new Map<string, GroupTreeItem>();
  const ungrouped: T[] = [];

  function ensureNode(path: string): GroupTreeItem {
    const existing = nodes.get(path);
    if (existing) return existing;
    const node: GroupTreeItem = {
      path,
      name: path.slice(path.lastIndexOf('/') + 1),
      parentPath: parentGroupPath(path),
      depth: groupDepth(path),
      directCount: 0,
      totalCount: 0,
      children: [],
    };
    nodes.set(path, node);
    return node;
  }

  // 先铺开显式模块路径及其所有父级，保证空模块也能出现
  extraPaths.forEach((raw) => {
    const path = normalizeGroupPath(raw);
    if (!path) return;
    const parts = path.split('/');
    for (let index = 1; index <= parts.length; index += 1) {
      ensureNode(parts.slice(0, index).join('/'));
    }
  });

  items.forEach((item) => {
    const path = normalizeGroupPath(item.group_path);
    if (!path) {
      ungrouped.push(item);
      return;
    }
    const parts = path.split('/');
    for (let index = 1; index <= parts.length; index += 1) {
      ensureNode(parts.slice(0, index).join('/'));
    }
    ensureNode(path).directCount += 1;
  });

  // 自底向上累计数量：先挂父亲，再按深度倒序累加
  const sorted = Array.from(nodes.values()).sort((left, right) => left.depth - right.depth);
  sorted.forEach((node) => {
    node.totalCount = node.directCount;
    if (node.parentPath) {
      const parent = nodes.get(node.parentPath);
      if (parent && !parent.children.some((child) => child.path === node.path)) {
        parent.children.push(node);
      }
    }
  });
  [...sorted].reverse().forEach((node) => {
    if (!node.parentPath) return;
    const parent = nodes.get(node.parentPath);
    if (parent) parent.totalCount += node.totalCount;
  });

  sorted.forEach((node) => {
    node.children.sort((left, right) => left.name.localeCompare(right.name));
  });

  const roots = sorted
    .filter((node) => !node.parentPath)
    .sort((left, right) => left.name.localeCompare(right.name));
  if (options.includeUngrouped && ungrouped.length > 0) {
    roots.push({
      path: '',
      name: '未分组',
      parentPath: '',
      depth: 0,
      directCount: ungrouped.length,
      totalCount: ungrouped.length,
      children: [],
    });
  }
  return roots;
}

/**
 * 按模块把条目分桶，键是原始 `group_path`（未分组为空串）。
 *
 * 与 `buildGroupTree` 的区别：这里保持「本模块直属条目」的分桶语义，
 * 用于在分组视图里直接渲染每个模块自己的表格。
 */
export function groupItemsByPath<T extends CountableItem>(
  items: readonly T[]
): Array<{ path: string; items: T[] }> {
  const buckets = new Map<string, T[]>();
  items.forEach((item) => {
    const path = normalizeGroupPath(item.group_path);
    const bucket = buckets.get(path);
    if (bucket) bucket.push(item);
    else buckets.set(path, [item]);
  });
  return Array.from(buckets.entries())
    .map(([path, bucketItems]) => ({ path, items: bucketItems }))
    .sort((left, right) => {
      // 未分组的排最后，其余按路径层级与名称排
      if (!left.path) return 1;
      if (!right.path) return -1;
      return (
        groupDepth(left.path) - groupDepth(right.path) ||
        left.path.localeCompare(right.path)
      );
    });
}

export interface GroupSelectOption {
  value: string;
  label: string;
  /** 缩进后的显示文本，便于父子模块在同一列表里可区分 */
  display: string;
}

/**
 * 生成「层级缩进」的模块下拉选项。
 *
 * @param paths 全部模块路径（可含重复/父级缺失）
 * @param options.includeEmpty 是否追加 value 为空串的「未分组」项
 */
export function buildGroupSelectOptions(
  paths: readonly string[],
  options: { includeEmpty?: boolean; emptyLabel?: string } = {}
): GroupSelectOption[] {
  const unique = new Set<string>();
  paths.forEach((raw) => {
    const path = normalizeGroupPath(raw);
    if (!path) return;
    const parts = path.split('/');
    for (let index = 1; index <= parts.length; index += 1) {
      unique.add(parts.slice(0, index).join('/'));
    }
  });

  const sorted = Array.from(unique).sort(
    (left, right) =>
      groupDepth(left) - groupDepth(right) || left.localeCompare(right)
  );

  const result: GroupSelectOption[] = sorted.map((path) => {
    const depth = groupDepth(path);
    const name = path.slice(path.lastIndexOf('/') + 1);
    return {
      value: path,
      label: path,
      display: `${'　'.repeat(Math.max(0, depth - 1))}${name}`,
    };
  });

  if (options.includeEmpty) {
    result.push({
      value: '',
      label: '未分组',
      display: options.emptyLabel || '未分组',
    });
  }
  return result;
}
