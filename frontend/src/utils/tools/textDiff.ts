export type TextDiffKind = 'same' | 'added' | 'removed';

export interface TextDiffLine {
  kind: TextDiffKind;
  leftNumber?: number;
  rightNumber?: number;
  text: string;
}

export interface TextDiffResult {
  lines: TextDiffLine[];
  added: number;
  removed: number;
  unchanged: number;
}

/** 文本对比选项：只影响「比较输入」，不改变输出的渲染结构。 */
export interface TextDiffOptions {
  /** 忽略每行行尾空白（空格 / 制表符）。 */
  ignoreTrailingWhitespace?: boolean;
  /** 忽略空行（含纯空白行）；行号仍按原文行号计。 */
  ignoreBlankLines?: boolean;
  /** 忽略大小写。 */
  ignoreCase?: boolean;
}

interface NormalizedLine {
  /** 原始行文本，用于展示。 */
  text: string;
  /** 归一化后的比较键。 */
  key: string;
  /** 原文行号（从 1 开始）。 */
  number: number;
}

function splitLines(text: string): string[] {
  if (text === '') return [];
  return text.replace(/\r\n?/g, '\n').split('\n');
}

function normalizeLines(text: string, options: TextDiffOptions): NormalizedLine[] {
  const result: NormalizedLine[] = [];
  splitLines(text).forEach((line, index) => {
    const withoutTrailing = options.ignoreTrailingWhitespace
      ? line.replace(/\s+$/, '')
      : line;
    if (options.ignoreBlankLines && withoutTrailing.trim() === '') return;
    result.push({
      text: line,
      key: options.ignoreCase ? withoutTrailing.toLowerCase() : withoutTrailing,
      number: index + 1,
    });
  });
  return result;
}

/**
 * 逐行对比两段文本（LCS 最长公共子序列）。
 *
 * @param left 原始文本
 * @param right 目标文本
 * @param options 可选对比选项；缺省时行为与无选项版本完全一致
 */
export function diffTextLines(
  left: string,
  right: string,
  options: TextDiffOptions = {}
): TextDiffResult {
  const leftLines = normalizeLines(left, options);
  const rightLines = normalizeLines(right, options);
  const rows = leftLines.length;
  const columns = rightLines.length;

  const table: number[][] = Array.from({ length: rows + 1 }, () =>
    new Array<number>(columns + 1).fill(0)
  );

  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = columns - 1; j >= 0; j -= 1) {
      table[i][j] =
        leftLines[i].key === rightLines[j].key
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const lines: TextDiffLine[] = [];
  let i = 0;
  let j = 0;

  while (i < rows && j < columns) {
    if (leftLines[i].key === rightLines[j].key) {
      lines.push({
        kind: 'same',
        leftNumber: leftLines[i].number,
        rightNumber: rightLines[j].number,
        text: leftLines[i].text,
      });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      lines.push({ kind: 'removed', leftNumber: leftLines[i].number, text: leftLines[i].text });
      i += 1;
    } else {
      lines.push({ kind: 'added', rightNumber: rightLines[j].number, text: rightLines[j].text });
      j += 1;
    }
  }

  while (i < rows) {
    lines.push({ kind: 'removed', leftNumber: leftLines[i].number, text: leftLines[i].text });
    i += 1;
  }

  while (j < columns) {
    lines.push({ kind: 'added', rightNumber: rightLines[j].number, text: rightLines[j].text });
    j += 1;
  }

  return {
    lines,
    added: lines.filter((line) => line.kind === 'added').length,
    removed: lines.filter((line) => line.kind === 'removed').length,
    unchanged: lines.filter((line) => line.kind === 'same').length,
  };
}

/** 行内字符差异片段：changed 为 true 的部分即差异字符。 */
export interface InlineDiffSegment {
  text: string;
  changed: boolean;
}

/** 一对「修改行」的行内差异：左侧（删除方）与右侧（新增方）各一组片段。 */
export interface InlineCharDiff {
  left: InlineDiffSegment[];
  right: InlineDiffSegment[];
}

export interface InlineDiffOptions {
  /** 忽略大小写：大小写不同的字符不视为差异。 */
  ignoreCase?: boolean;
}

function buildSegments(
  text: string,
  changedStart: number,
  changedEnd: number
): InlineDiffSegment[] {
  const segments: InlineDiffSegment[] = [];
  if (changedStart > 0) {
    segments.push({ text: text.slice(0, changedStart), changed: false });
  }
  if (changedEnd > changedStart) {
    segments.push({ text: text.slice(changedStart, changedEnd), changed: true });
  }
  if (changedEnd < text.length) {
    segments.push({ text: text.slice(changedEnd), changed: false });
  }
  return segments;
}

/**
 * 两个等长语义行的行内字符差异（前缀 / 后缀公共部分保持不变，中间记为差异）。
 *
 * 典型用途：把「一对修改行（一删一增）」中真正变化的字符高亮出来，
 * 效果等价于 GitHub diff 的行内高亮。
 */
export function diffCharsInline(
  left: string,
  right: string,
  options: InlineDiffOptions = {}
): InlineCharDiff {
  const charsEqual = (a: string, b: string) =>
    options.ignoreCase
      ? a.toLowerCase() === b.toLowerCase()
      : a === b;

  const maxPrefix = Math.min(left.length, right.length);
  let start = 0;
  while (start < maxPrefix && charsEqual(left[start], right[start])) {
    start += 1;
  }

  let endLeft = left.length;
  let endRight = right.length;
  while (endLeft > start && endRight > start && charsEqual(left[endLeft - 1], right[endRight - 1])) {
    endLeft -= 1;
    endRight -= 1;
  }

  return {
    left: buildSegments(left, start, endLeft),
    right: buildSegments(right, start, endRight),
  };
}
