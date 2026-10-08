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
