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

function splitLines(text: string): string[] {
  if (text === '') return [];
  return text.replace(/\r\n?/g, '\n').split('\n');
}

export function diffTextLines(left: string, right: string): TextDiffResult {
  const leftLines = splitLines(left);
  const rightLines = splitLines(right);
  const rows = leftLines.length;
  const columns = rightLines.length;

  const table: number[][] = Array.from({ length: rows + 1 }, () =>
    new Array<number>(columns + 1).fill(0)
  );

  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = columns - 1; j >= 0; j -= 1) {
      table[i][j] =
        leftLines[i] === rightLines[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const lines: TextDiffLine[] = [];
  let i = 0;
  let j = 0;

  while (i < rows && j < columns) {
    if (leftLines[i] === rightLines[j]) {
      lines.push({
        kind: 'same',
        leftNumber: i + 1,
        rightNumber: j + 1,
        text: leftLines[i],
      });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      lines.push({ kind: 'removed', leftNumber: i + 1, text: leftLines[i] });
      i += 1;
    } else {
      lines.push({ kind: 'added', rightNumber: j + 1, text: rightLines[j] });
      j += 1;
    }
  }

  while (i < rows) {
    lines.push({ kind: 'removed', leftNumber: i + 1, text: leftLines[i] });
    i += 1;
  }

  while (j < columns) {
    lines.push({ kind: 'added', rightNumber: j + 1, text: rightLines[j] });
    j += 1;
  }

  return {
    lines,
    added: lines.filter((line) => line.kind === 'added').length,
    removed: lines.filter((line) => line.kind === 'removed').length,
    unchanged: lines.filter((line) => line.kind === 'same').length,
  };
}
