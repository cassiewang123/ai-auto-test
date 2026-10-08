export type LogLevel = 'ERROR' | 'WARN' | 'INFO' | 'DEBUG' | 'OTHER';

export interface ParsedLogEntry {
  lineNumber: number;
  timestamp?: string;
  level: LogLevel;
  message: string;
  raw: string;
}

export interface LogSummary {
  total: number;
  byLevel: Record<LogLevel, number>;
  errorRate: number;
  firstTimestamp?: string;
  lastTimestamp?: string;
  hours: Array<{ hour: string; count: number }>;
}

export interface LogFilterOptions {
  levels: LogLevel[];
  keyword: string;
  caseSensitive?: boolean;
  useRegex?: boolean;
}

const levelPattern = /\b(TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b/i;
const timestampPattern =
  /(?:^|\s)(\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+|\d{2}\/\d{2}\/\d{4} [0-9:]+|\[[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2} [0-9:]+\])/;

function normalizeLevel(value: string): LogLevel {
  const level = value.toUpperCase();
  if (level === 'ERROR' || level === 'FATAL' || level === 'CRITICAL') return 'ERROR';
  if (level === 'WARN' || level === 'WARNING') return 'WARN';
  if (level === 'INFO') return 'INFO';
  if (level === 'DEBUG' || level === 'TRACE') return 'DEBUG';
  return 'OTHER';
}

export function parseLogText(text: string): ParsedLogEntry[] {
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((raw, index) => ({ raw, index }))
    .filter((item) => item.raw.trim() !== '')
    .map(({ raw, index }) => {
      const timestampMatch = raw.match(timestampPattern);
      const levelMatch = raw.match(levelPattern);
      const level = levelMatch ? normalizeLevel(levelMatch[1]) : 'OTHER';
      const message = raw
        .replace(timestampMatch?.[0] ?? '', '')
        .replace(levelMatch?.[0] ?? '', '')
        .trim();

      return {
        lineNumber: index + 1,
        timestamp: timestampMatch?.[1],
        level,
        message: message || raw.trim(),
        raw,
      };
    });
}

export function summarizeLogs(entries: ParsedLogEntry[]): LogSummary {
  const byLevel: Record<LogLevel, number> = {
    ERROR: 0,
    WARN: 0,
    INFO: 0,
    DEBUG: 0,
    OTHER: 0,
  };
  const hourCounts = new Map<string, number>();

  entries.forEach((entry) => {
    byLevel[entry.level] += 1;
    const timestamp = entry.timestamp?.replace(/^\[|\]$/g, '');
    const hourMatch = timestamp?.match(/(\d{1,2}):\d{2}/);
    if (hourMatch) {
      const hour = `${hourMatch[1].padStart(2, '0')}:00`;
      hourCounts.set(hour, (hourCounts.get(hour) ?? 0) + 1);
    }
  });

  const timestamps = entries
    .map((entry) => entry.timestamp?.replace(/^\[|\]$/g, ''))
    .filter((item): item is string => Boolean(item));

  return {
    total: entries.length,
    byLevel,
    errorRate: entries.length === 0 ? 0 : byLevel.ERROR / entries.length,
    firstTimestamp: timestamps[0],
    lastTimestamp: timestamps[timestamps.length - 1],
    hours: Array.from(hourCounts.entries())
      .map(([hour, count]) => ({ hour, count }))
      .sort((left, right) => left.hour.localeCompare(right.hour)),
  };
}

export function filterLogs(
  entries: ParsedLogEntry[],
  options: LogFilterOptions
): ParsedLogEntry[] {
  const levels = options.levels.length > 0 ? new Set(options.levels) : null;
  const keyword = options.keyword.trim();
  const flags = options.caseSensitive ? '' : 'i';

  let matcher: ((value: string) => boolean) | null = null;
  if (keyword !== '') {
    if (options.useRegex) {
      try {
        const regex = new RegExp(keyword, flags);
        matcher = (value) => regex.test(value);
      } catch {
        matcher = () => false;
      }
    } else {
      const needle = options.caseSensitive ? keyword : keyword.toLowerCase();
      matcher = (value) =>
        (options.caseSensitive ? value : value.toLowerCase()).includes(needle);
    }
  }

  return entries.filter((entry) => {
    if (levels && !levels.has(entry.level)) return false;
    return !matcher || matcher(entry.raw);
  });
}
