export interface TimestampConversion {
  seconds: number;
  milliseconds: number;
  iso: string;
  local: string;
  valid: boolean;
  error?: string;
}

export function dateToTimestamp(input: string): TimestampConversion {
  const value = input.trim();
  if (value === '') {
    return {
      seconds: 0,
      milliseconds: 0,
      iso: '',
      local: '',
      valid: false,
      error: '请输入日期时间',
    };
  }

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return {
      seconds: 0,
      milliseconds: 0,
      iso: '',
      local: '',
      valid: false,
      error: '无法解析该日期时间，建议使用 2026-10-08 13:47:59 或 ISO 格式',
    };
  }

  return {
    seconds: Math.floor(timestamp / 1000),
    milliseconds: timestamp,
    iso: new Date(timestamp).toISOString(),
    local: formatLocalDate(new Date(timestamp)),
    valid: true,
  };
}

export function timestampToDate(input: string): TimestampConversion {
  const value = input.trim();
  if (value === '') {
    return {
      seconds: 0,
      milliseconds: 0,
      iso: '',
      local: '',
      valid: false,
      error: '请输入时间戳',
    };
  }
  if (!/^-?\d+$/.test(value)) {
    return {
      seconds: 0,
      milliseconds: 0,
      iso: '',
      local: '',
      valid: false,
      error: '时间戳必须是整数',
    };
  }

  const numeric = Number(value);
  const milliseconds = Math.abs(numeric) < 1e12 ? numeric * 1000 : numeric;
  const date = new Date(milliseconds);

  if (Number.isNaN(date.getTime())) {
    return {
      seconds: 0,
      milliseconds: 0,
      iso: '',
      local: '',
      valid: false,
      error: '时间戳超出可解析范围',
    };
  }

  return {
    seconds: Math.floor(milliseconds / 1000),
    milliseconds,
    iso: date.toISOString(),
    local: formatLocalDate(date),
    valid: true,
  };
}

export function formatLocalDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
