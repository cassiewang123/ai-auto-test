import { describe, expect, it } from 'vitest';
import { diffTextLines } from './textDiff';
import { countText, wordFrequencies } from './textMetrics';
import { evaluateRegex, replaceRegex } from './regexTool';
import { transformText } from './encodingTool';
import { dateToTimestamp, timestampToDate } from './timestampTool';
import { generateData } from './randomData';
import { filterLogs, parseLogText, summarizeLogs } from './logAnalysis';

describe('text diff tools', () => {
  it('reports added, removed and unchanged lines', () => {
    const result = diffTextLines('a\nb\nc', 'a\nx\nc');
    expect(result.added).toBe(1);
    expect(result.removed).toBe(1);
    expect(result.unchanged).toBe(2);
    expect(result.lines.map((line) => line.kind)).toEqual([
      'same',
      'removed',
      'added',
      'same',
    ]);
  });
});

describe('text metrics tools', () => {
  it('counts mixed Chinese and English text', () => {
    const result = countText('你好 world\nsecond line');
    expect(result.chineseCharacters).toBe(2);
    expect(result.lines).toBe(2);
    expect(result.words).toBe(4);
    expect(result.bytes).toBeGreaterThan(result.characters);
  });

  it('ranks frequent tokens', () => {
    expect(wordFrequencies('api api test').slice(0, 2)).toEqual([
      { word: 'api', count: 2 },
      { word: 'test', count: 1 },
    ]);
  });
});

describe('regex tools', () => {
  it('returns matches and groups', () => {
    const result = evaluateRegex('(\\d+)-(\\d+)', 'g', '12-34, 56-78');
    expect(result.valid).toBe(true);
    expect(result.matches).toHaveLength(2);
    expect(result.matches[0].groups).toEqual(['12', '34']);
  });

  it('reports invalid patterns and performs replacement', () => {
    expect(evaluateRegex('([', 'g', 'x').valid).toBe(false);
    expect(replaceRegex('\\d+', 'g', 'a1b2', '#')).toBe('a#b#');
  });
});

describe('encoding tools', () => {
  it('round-trips Base64, URL, Hex, Unicode and HTML', () => {
    const text = '测试 <tag> & 1';
    (['base64', 'url', 'hex', 'unicode', 'html'] as const).forEach((kind) => {
      const encoded = transformText(text, kind, 'encode');
      expect(encoded).not.toBe(text);
      expect(transformText(encoded, kind, 'decode')).toBe(text);
    });
  });
});

describe('timestamp tools', () => {
  it('converts dates and timestamps', () => {
    const date = dateToTimestamp('2026-10-08 13:47:59');
    expect(date.valid).toBe(true);
    expect(date.seconds).toBeGreaterThan(0);
    const roundTrip = timestampToDate(String(date.seconds));
    expect(roundTrip.valid).toBe(true);
    expect(roundTrip.milliseconds).toBe(date.milliseconds);
  });

  it('rejects malformed timestamps', () => {
    expect(timestampToDate('abc').valid).toBe(false);
  });
});

describe('random data tools', () => {
  it('generates the requested number of values', () => {
    const values = generateData('email', 5);
    expect(values).toHaveLength(5);
    values.forEach((value) => expect(value).toContain('@'));
  });
});

describe('log analysis tools', () => {
  const logs = [
    '2026-10-08 13:00:00 INFO started',
    '2026-10-08 13:01:00 WARN slow response',
    '2026-10-08 13:02:00 ERROR request failed',
  ].join('\n');

  it('parses and summarizes levels', () => {
    const entries = parseLogText(logs);
    const summary = summarizeLogs(entries);
    expect(entries).toHaveLength(3);
    expect(summary.byLevel.ERROR).toBe(1);
    expect(summary.byLevel.WARN).toBe(1);
    expect(summary.errorRate).toBeCloseTo(1 / 3);
  });

  it('filters logs by level and keyword', () => {
    const entries = parseLogText(logs);
    expect(filterLogs(entries, { levels: ['ERROR'], keyword: '' })).toHaveLength(1);
    expect(
      filterLogs(entries, { levels: [], keyword: 'slow', caseSensitive: false })
    ).toHaveLength(1);
  });
});
