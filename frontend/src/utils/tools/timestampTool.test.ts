import { describe, expect, it } from 'vitest';
import {
  dateToTimestamp,
  formatLocalDate,
  timestampToDate,
} from './timestampTool';

describe('timestampTool 时区支持', () => {
  it('缺省 timeZone 时保持本地默认行为不变', () => {
    const date = dateToTimestamp('2026-10-08 13:47:59');
    expect(date.valid).toBe(true);
    // 与历史实现一致：按浏览器本地时区解析并按本地时区回显
    expect(date.local).toBe(formatLocalDate(new Date(date.milliseconds)));
    expect(date.iso).toBe(new Date(date.milliseconds).toISOString());

    const roundTrip = timestampToDate(String(date.seconds));
    expect(roundTrip.valid).toBe(true);
    expect(roundTrip.milliseconds).toBe(date.milliseconds);
    expect(roundTrip.local).toBe(date.local);
  });

  it('UTC：无时区输入按 UTC 解析，时间戳按 UTC 回显', () => {
    const date = dateToTimestamp('2026-10-08 13:47:59', 'UTC');
    expect(date.valid).toBe(true);
    expect(date.milliseconds).toBe(Date.UTC(2026, 9, 8, 13, 47, 59));
    expect(date.local).toBe('2026-10-08 13:47:59');
    expect(date.iso).toBe('2026-10-08T13:47:59.000Z');

    const converted = timestampToDate(String(date.seconds), 'UTC');
    expect(converted.local).toBe('2026-10-08 13:47:59');
  });

  it('指定时区往返：Asia/Shanghai 解析与回显一致', () => {
    const date = dateToTimestamp('2026-10-08 13:47:59', 'Asia/Shanghai');
    expect(date.valid).toBe(true);
    // 东八区 13:47:59 对应 UTC 05:47:59
    expect(date.milliseconds).toBe(Date.UTC(2026, 9, 8, 5, 47, 59));
    expect(date.local).toBe('2026-10-08 13:47:59');

    const back = timestampToDate(String(date.seconds), 'Asia/Shanghai');
    expect(back.valid).toBe(true);
    expect(back.local).toBe('2026-10-08 13:47:59');
  });

  it('不同时区解析同一挂钟时间得到固定偏移（上海 vs 东京差 1 小时）', () => {
    const shanghai = dateToTimestamp('2026-10-08 13:47:59', 'Asia/Shanghai');
    const tokyo = dateToTimestamp('2026-10-08 13:47:59', 'Asia/Tokyo');
    expect(shanghai.milliseconds - tokyo.milliseconds).toBe(60 * 60 * 1000);
  });

  it('formatLocalDate 直接支持时区，非法时区回退本地', () => {
    const instant = new Date(Date.UTC(2026, 9, 8, 13, 47, 59));
    expect(formatLocalDate(instant, 'UTC')).toBe('2026-10-08 13:47:59');
    expect(formatLocalDate(instant, 'Asia/Shanghai')).toBe('2026-10-08 21:47:59');
    // 非法时区不抛错，回退为本地时区格式化
    expect(formatLocalDate(instant, 'Not/AZone')).toBe(
      `${instant.getFullYear()}-${String(instant.getMonth() + 1).padStart(2, '0')}-${String(
        instant.getDate()
      ).padStart(2, '0')} ${String(instant.getHours()).padStart(2, '0')}:${String(
        instant.getMinutes()
      ).padStart(2, '0')}:${String(instant.getSeconds()).padStart(2, '0')}`
    );
  });

  it('带显式偏移的 ISO 字符串忽略 timeZone 参数，按自带偏移解析', () => {
    const date = dateToTimestamp('2026-10-08T13:47:59+08:00', 'America/New_York');
    expect(date.valid).toBe(true);
    expect(date.milliseconds).toBe(Date.UTC(2026, 9, 8, 5, 47, 59));
  });
});
