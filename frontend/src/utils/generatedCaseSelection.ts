/**
 * 生成结果表的行键与「按选中项取用例」逻辑。
 *
 * 背景：表格 rowKey 一旦是业务字段拼出来的字符串（如 `标题-场景`），
 * `selectedRowKeys` 里保存的就是这些字符串，而不是数组下标。若导入时
 * 仍按下标去取 `generated[key]`，取到的全是 undefined，JSON 序列化后
 * 变成 `[null, null, ...]`，后端只会报「cases.0: Input should be a valid
 * dictionary」。这里把「行键生成」和「按行键取用例」收敛到一处，保证
 * 表格选中与导入使用的是同一套键。
 */

export type RowKey = string | number;

/** 生成结果行：业务字段 + 表格行键。 */
export type KeyedCase<T> = T & { rowKey: string };

type KeyableCase = {
  title?: string;
  case_type?: string;
};

/**
 * 给生成结果补上表格行键。
 *
 * 行键带上序号，避免标题与场景都相同的用例互相覆盖；每次重新生成都会
 * 整体替换列表，因此序号只在当前一轮生成结果内有效。
 */
export function buildKeyedCases<T extends KeyableCase>(
  cases: readonly T[] | null | undefined
): KeyedCase<T>[] {
  return (cases || []).map((item, index) => ({
    ...item,
    rowKey: `${index}::${item?.title ?? ''}::${item?.case_type ?? ''}`,
  }));
}

/**
 * 按表格选中项取出对应用例，保持生成结果原有顺序。
 *
 * `keys` 允许是 AntD 回传的任意 Key 类型；未知键（例如上一轮生成遗留的
 * 行键）会被忽略，不会退化成 `undefined` 占位。
 */
export function pickSelectedCases<T>(
  rows: readonly KeyedCase<T>[],
  keys: readonly RowKey[] | null | undefined
): KeyedCase<T>[] {
  if (!rows || rows.length === 0) return [];
  const wanted = new Set((keys || []).map((key) => String(key)));
  if (wanted.size === 0) return [];
  return rows.filter((row) => wanted.has(String(row.rowKey)));
}

/** 去掉行键，得到可直接提交给后端的用例数组。 */
export function toImportCases<T>(rows: readonly KeyedCase<T>[]): T[] {
  return rows.map(({ rowKey: _rowKey, ...rest }) => rest as T);
}
