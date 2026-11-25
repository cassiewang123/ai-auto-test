export interface TimestampConversion {
  seconds: number;
  milliseconds: number;
  iso: string;
  local: string;
  valid: boolean;
  error?: string;
}

/** 无时区信息的日期时间：2026-10-08、2026-10-08 13:47、2026-10-08 13:47:59（空格或 T 分隔）。 */
const NAIVE_DATETIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/;

interface WallClock {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/** 读取某一时刻在指定 IANA 时区的挂钟时间；时区非法时返回 null。 */
function readWallClock(date: Date, timeZone: string): WallClock | null {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).formatToParts(date);
    const read = (type: string) =>
      Number(parts.find((part) => part.type === type)?.value ?? '0');
    let hour = read('hour');
    if (hour === 24) hour = 0; // 个别环境 hour12:false 会输出 24 点
    return {
      year: read('year'),
      month: read('month'),
      day: read('day'),
      hour,
      minute: read('minute'),
      second: read('second'),
    };
  } catch {
    return null;
  }
}

/**
 * 把「无时区信息的日期时间」按指定时区解析为 UTC 毫秒时间戳。
 *
 * 先按 UTC 猜一个时刻，再用 Intl 读出该时刻在目标时区的挂钟时间求出偏移，
 * 迭代两轮收敛（覆盖夏令时边界）。带 Z / ±hh:mm 的 ISO 字符串或非法输入
 * 交回原生 Date 解析；timeZone 缺省时等价于原生解析（本地时区）。
 */
function parseNaiveInTimeZone(value: string, timeZone?: string): number {
  if (!timeZone) return new Date(value).getTime();

  const matched = NAIVE_DATETIME_PATTERN.exec(value);
  if (!matched) return new Date(value).getTime();

  const [, year, month, day, hour, minute, second] = matched;
  const utcGuess = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour ?? 0),
    Number(minute ?? 0),
    Number(second ?? 0)
  );

  let timestamp = utcGuess;
  for (let round = 0; round < 2; round += 1) {
    const wall = readWallClock(new Date(timestamp), timeZone);
    if (!wall) return new Date(value).getTime();
    const wallAsUtc = Date.UTC(
      wall.year,
      wall.month - 1,
      wall.day,
      wall.hour,
      wall.minute,
      wall.second
    );
    timestamp = utcGuess - (wallAsUtc - timestamp);
  }
  return timestamp;
}

function invalidResult(error: string): TimestampConversion {
  return {
    seconds: 0,
    milliseconds: 0,
    iso: '',
    local: '',
    valid: false,
    error,
  };
}

/**
 * 日期时间转时间戳。
 *
 * @param input 日期时间字符串
 * @param timeZone 可选 IANA 时区（如 'Asia/Shanghai'、'UTC'）；缺省按浏览器本地时区解析，行为与历史版本一致
 */
export function dateToTimestamp(
  input: string,
  timeZone?: string
): TimestampConversion {
  const value = input.trim();
  if (value === '') {
    return invalidResult('请输入日期时间');
  }

  const timestamp = parseNaiveInTimeZone(value, timeZone);
  if (Number.isNaN(timestamp)) {
    return invalidResult('无法解析该日期时间，建议使用 2026-10-08 13:47:59 或 ISO 格式');
  }

  return {
    seconds: Math.floor(timestamp / 1000),
    milliseconds: timestamp,
    iso: new Date(timestamp).toISOString(),
    local: formatLocalDate(new Date(timestamp), timeZone),
    valid: true,
  };
}

/**
 * 时间戳转日期时间。
 *
 * @param input 10 位秒级或 13 位毫秒级时间戳
 * @param timeZone 可选 IANA 时区；缺省展示浏览器本地时间，行为与历史版本一致
 */
export function timestampToDate(
  input: string,
  timeZone?: string
): TimestampConversion {
  const value = input.trim();
  if (value === '') {
    return invalidResult('请输入时间戳');
  }
  if (!/^-?\d+$/.test(value)) {
    return invalidResult('时间戳必须是整数');
  }

  const numeric = Number(value);
  const milliseconds = Math.abs(numeric) < 1e12 ? numeric * 1000 : numeric;
  const date = new Date(milliseconds);

  if (Number.isNaN(date.getTime())) {
    return invalidResult('时间戳超出可解析范围');
  }

  return {
    seconds: Math.floor(milliseconds / 1000),
    milliseconds,
    iso: date.toISOString(),
    local: formatLocalDate(date, timeZone),
    valid: true,
  };
}

/**
 * 格式化为 `YYYY-MM-DD HH:mm:ss`。
 *
 * @param date 时刻
 * @param timeZone 可选 IANA 时区；缺省使用浏览器本地时区（与历史版本一致），非法时区自动回退本地
 */
export function formatLocalDate(date: Date, timeZone?: string): string {
  if (timeZone) {
    const wall = readWallClock(date, timeZone);
    if (wall) {
      return [
        `${wall.year}-${pad(wall.month)}-${pad(wall.day)}`,
        `${pad(wall.hour)}:${pad(wall.minute)}:${pad(wall.second)}`,
      ].join(' ');
    }
  }
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
