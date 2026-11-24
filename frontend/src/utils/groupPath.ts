/**
 * 接口分组路径匹配工具.
 *
 * 接口通过 `group_path` 归组，路径以 `/` 表示层级，例如：
 *   swgd-imap-content
 *   swgd-imap-content/ApiType 码表
 *
 * 选中某个分组时，应命中「该分组本身 + 其下所有子分组」的接口，
 * 否则选择顶级模块会显示 0 个接口。
 */
export function matchesGroupPath(
  caseGroupPath: string | null | undefined,
  selectedGroupPath: string
): boolean {
  const current = (caseGroupPath || '').trim();
  const selected = (selectedGroupPath || '').trim();

  // 空分组路径表示「未分组」
  if (!selected) return current === '';
  return current === selected || current.startsWith(`${selected}/`);
}

/**
 * 从完整分组路径中拆出叶子名称与父级路径，用于下拉选项的两行展示。
 */
export function splitGroupPath(path: string): { leaf: string; prefix: string } {
  const normalized = (path || '').trim().replace(/\/+$/, '');
  if (!normalized) return { leaf: '', prefix: '' };
  const index = normalized.lastIndexOf('/');
  if (index < 0) return { leaf: normalized, prefix: '' };
  return {
    leaf: normalized.slice(index + 1),
    prefix: normalized.slice(0, index),
  };
}
