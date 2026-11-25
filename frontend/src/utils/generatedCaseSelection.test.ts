import { describe, expect, it } from 'vitest';

import {
  buildKeyedCases,
  pickSelectedCases,
  toImportCases,
} from './generatedCaseSelection';

type Case = {
  title: string;
  case_type: string;
  method: string;
  url: string;
  priority: string;
};

function makeCases(): Case[] {
  return [
    {
      title: '01 新增反馈 正常请求',
      case_type: 'normal',
      method: 'POST',
      url: '/feedback',
      priority: 'P0',
    },
    {
      title: '参数 content 缺失时返回校验错误',
      case_type: 'exception',
      method: 'POST',
      url: '/feedback',
      priority: 'P1',
    },
  ];
}

describe('buildKeyedCases', () => {
  it('为每条用例生成唯一的行键', () => {
    const rows = buildKeyedCases(makeCases());
    expect(rows).toHaveLength(2);
    expect(new Set(rows.map((row) => row.rowKey)).size).toBe(2);
    expect(rows[0].title).toBe('01 新增反馈 正常请求');
  });

  it('标题与场景都相同的用例也能区分', () => {
    const rows = buildKeyedCases([
      { title: '重复标题', case_type: 'normal' },
      { title: '重复标题', case_type: 'normal' },
    ]);
    expect(rows[0].rowKey).not.toBe(rows[1].rowKey);
  });

  it('空输入返回空数组', () => {
    expect(buildKeyedCases(undefined)).toEqual([]);
    expect(buildKeyedCases([])).toEqual([]);
  });
});

describe('pickSelectedCases', () => {
  it('按表格行键（字符串）取回选中的用例', () => {
    const rows = buildKeyedCases(makeCases());
    const selected = [rows[1].rowKey];

    const picked = pickSelectedCases(rows, selected);

    expect(picked).toHaveLength(1);
    expect(picked[0].title).toBe('参数 content 缺失时返回校验错误');
  });

  it('保持生成结果的原始顺序', () => {
    const rows = buildKeyedCases(makeCases());
    const picked = pickSelectedCases(rows, [rows[1].rowKey, rows[0].rowKey]);
    expect(picked.map((row) => row.title)).toEqual([
      '01 新增反馈 正常请求',
      '参数 content 缺失时返回校验错误',
    ]);
  });

  it('不再把数组下标当成行键（回归：导入时报 cases.0 不是字典）', () => {
    const rows = buildKeyedCases(makeCases());
    expect(pickSelectedCases(rows, [0, 1])).toEqual([]);
  });

  it('忽略上一轮生成遗留的行键', () => {
    const rows = buildKeyedCases(makeCases());
    const picked = pickSelectedCases(rows, ['9::已失效::normal', rows[0].rowKey]);
    expect(picked.map((row) => row.title)).toEqual(['01 新增反馈 正常请求']);
  });

  it('没有选中项时返回空数组', () => {
    const rows = buildKeyedCases(makeCases());
    expect(pickSelectedCases(rows, [])).toEqual([]);
    expect(pickSelectedCases(rows, undefined)).toEqual([]);
    expect(pickSelectedCases([], ['0::x::normal'])).toEqual([]);
  });
});

describe('toImportCases', () => {
  it('提交前去掉行键，其余字段保持不变', () => {
    const rows = buildKeyedCases(makeCases());
    const payload = toImportCases(rows);

    expect(payload).toHaveLength(2);
    expect(payload[0]).not.toHaveProperty('rowKey');
    expect(payload[0]).toEqual({
      title: '01 新增反馈 正常请求',
      case_type: 'normal',
      method: 'POST',
      url: '/feedback',
      priority: 'P0',
    });
  });
});
