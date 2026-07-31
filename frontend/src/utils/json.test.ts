import { describe, expect, it } from 'vitest';
import { validateJsonText } from './json';

describe('validateJsonText', () => {
  it('accepts all JSON value types while requiring an object when requested', () => {
    expect(validateJsonText('[1, 2, 3]', { expectedType: 'any' }).valid).toBe(true);
    expect(validateJsonText('[1, 2, 3]', { expectedType: 'object' })).toMatchObject({
      valid: false,
      error: '请输入 JSON 对象',
    });
    expect(validateJsonText('{"id": 1}', { expectedType: 'object' }).value).toEqual({
      id: 1,
    });
  });

  it('reports invalid JSON without throwing from the editor validation path', () => {
    const result = validateJsonText('{"id": }', { allowEmpty: false });

    expect(result.valid).toBe(false);
    expect(result.error).toContain('JSON 格式不正确');
  });
});
