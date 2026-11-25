export interface RegexMatch {
  index: number;
  value: string;
  groups: string[];
  namedGroups: Record<string, string>;
}

export interface RegexEvaluation {
  valid: boolean;
  error?: string;
  matches: RegexMatch[];
}

export function evaluateRegex(
  pattern: string,
  flags: string,
  text: string
): RegexEvaluation {
  if (pattern === '') {
    return { valid: true, matches: [] };
  }

  let regex: RegExp;
  try {
    regex = new RegExp(pattern, flags);
  } catch (error) {
    return {
      valid: false,
      error: error instanceof Error ? error.message : '正则表达式无效',
      matches: [],
    };
  }

  if (text === '') {
    return { valid: true, matches: [] };
  }

  const matches: RegexMatch[] = [];
  const globalRegex = regex.global ? regex : new RegExp(regex.source, `${regex.flags}g`);
  let match: RegExpExecArray | null = globalRegex.exec(text);
  let guard = 0;

  while (match && guard < 10000) {
    matches.push({
      index: match.index,
      value: match[0],
      groups: match.slice(1).map((group) => group ?? ''),
      namedGroups: match.groups ? { ...match.groups } : {},
    });
    if (match[0] === '') globalRegex.lastIndex += 1;
    match = globalRegex.exec(text);
    guard += 1;
  }

  return { valid: true, matches };
}

export function replaceRegex(
  pattern: string,
  flags: string,
  text: string,
  replacement: string
): string {
  if (pattern === '') return text;
  const flagsWithoutG = flags.replace(/g/g, '');
  return text.replace(new RegExp(pattern, `${flagsWithoutG}g`), replacement);
}

/** 高亮预览片段：matched 为 true 的片段即命中部分。 */
export interface RegexHighlightSegment {
  text: string;
  matched: boolean;
}

/**
 * 依据 evaluateRegex 的匹配结果把原文切分为「命中 / 未命中」片段，
 * 供正则测试页渲染高亮预览；片段顺序拼接后与原文完全一致。
 *
 * 对越界 / 零长度的历史匹配做了防御，保证任何输入都不抛错。
 */
export function buildHighlightSegments(
  text: string,
  matches: RegexMatch[]
): RegexHighlightSegment[] {
  const segments: RegexHighlightSegment[] = [];
  let cursor = 0;

  for (const match of matches) {
    const start = Math.max(0, Math.min(match.index, text.length));
    const end = Math.max(
      start,
      Math.min(match.index + match.value.length, text.length)
    );
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), matched: false });
    }
    if (end > start) {
      segments.push({ text: text.slice(start, end), matched: true });
    }
    cursor = Math.max(cursor, end);
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), matched: false });
  }

  return segments;
}
