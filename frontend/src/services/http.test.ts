import { describe, expect, it } from 'vitest';
import { formatDetail } from './http';

describe('formatDetail', () => {
  it('字符串原样返回', () => {
    expect(formatDetail('请求失败')).toBe('请求失败');
  });

  it('把 FastAPI 校验错误数组格式化为可读文本', () => {
    const detail = [
      {
        loc: ['body', 'interface_name'],
        msg: 'String should have at most 256 characters',
        type: 'string_too_long',
      },
      {
        loc: ['body', 'cases', 0, 'title'],
        msg: 'Field required',
        type: 'missing',
      },
    ];
    const text = formatDetail(detail);
    expect(text).toContain('interface_name');
    expect(text).toContain('at most 256 characters');
    expect(text).toContain('cases.0.title');
    // 不能再出现 [object Object]
    expect(text).not.toContain('[object Object]');
  });

  it('空或缺失时返回 null', () => {
    expect(formatDetail(undefined)).toBeNull();
    expect(formatDetail(null as any)).toBeNull();
    expect(formatDetail([])).toBeNull();
  });
});
