/**
 * 变量占位符输入提示（`{{var}}`）的纯函数实现。
 *
 * 供 URL 输入框与 KV 编辑器的值输入复用：检测文本末尾未闭合的 `{{xxx`，
 * 给出可点击补全的候选项（value 已替换成补全后的完整文本）。
 */

/** 候选项：label 展示变量名，value 是补全后的完整文本 */
export interface VariableSuggestion {
  label: string;
  value: string;
}

/** 检测文本末尾未闭合的 {{ 占位符，返回已输入的变量名片段 */
export function matchOpenVariablePlaceholder(text: string): string | null {
  const value = String(text ?? '');
  const match = /\{\{([^{}]*)$/.exec(value);
  return match ? match[1] : null;
}

/**
 * 依据当前输入文本生成变量补全候选。
 *
 * - 没有 `{{` 或已闭合（如 `{{a}}`）时返回空数组（不弹提示）
 * - 候选按已输入片段做大小写不敏感的包含匹配
 * - 选中后整段 `{{xxx` 被替换为 `{{name}}`
 */
export function buildVariableSuggestions(
  text: string,
  names: string[]
): VariableSuggestion[] {
  const typed = matchOpenVariablePlaceholder(text);
  if (typed === null) return [];

  const keyword = typed.trim().toLowerCase();
  const candidates = (names ?? []).filter((name) => {
    if (!name) return false;
    if (!keyword) return true;
    return name.toLowerCase().includes(keyword);
  });

  return candidates
    .slice()
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({
      label: name,
      value: String(text ?? '').replace(/\{\{[^{}]*$/, `{{${name}}}`),
    }));
}
