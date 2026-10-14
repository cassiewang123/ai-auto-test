import { describe, expect, it } from 'vitest';
import { compactSql, formatSql, normalizeSqlError } from './sqlFormatter';

const simple = 'select a,b from t where x=1 order by a desc;';

describe('sqlFormatter.formatSql', () => {
  it('关键字大写并换行缩进', () => {
    const output = formatSql(simple, {
      language: 'sql',
      keywordCase: 'upper',
      indent: 2,
      indentStyle: 'standard',
      logicalOperatorNewline: 'before',
      expressionWidth: 80,
      linesBetweenQueries: 2,
    });
    expect(output).toContain('SELECT');
    expect(output).toContain('\n  a,');
    expect(output).toContain('FROM');
    expect(output).toContain('ORDER BY');
    expect(output).not.toContain('select');
  });

  it('关键字可以保持原样', () => {
    const output = formatSql('select 1', {
      language: 'sql',
      keywordCase: 'preserve',
      indent: 2,
      indentStyle: 'standard',
      logicalOperatorNewline: 'before',
      expressionWidth: 80,
      linesBetweenQueries: 2,
    });
    expect(output).toContain('select');
    expect(output).not.toContain('SELECT');
  });

  it('支持 Oracle 与 Hive 方言', () => {
    const oracle = formatSql('select * from dual where rownum<=10', {
      language: 'plsql',
      keywordCase: 'upper',
      indent: 2,
      indentStyle: 'standard',
      logicalOperatorNewline: 'before',
      expressionWidth: 80,
      linesBetweenQueries: 2,
    });
    expect(oracle).toContain('SELECT');

    const hive = formatSql('select get_json_object(col,"$.name") from t', {
      language: 'hive',
      keywordCase: 'upper',
      indent: 2,
      indentStyle: 'standard',
      logicalOperatorNewline: 'before',
      expressionWidth: 80,
      linesBetweenQueries: 2,
    });
    // Hive 的 get_json_object 不是解析器内置关键字，保持原样即可，重点是整句结构被格式化
    expect(hive).toContain('SELECT');
    expect(hive).toContain('get_json_object(col, "$.name")');
    expect(hive).toContain('FROM');
  });

  it('保留字符串字面量中的空格', () => {
    const output = formatSql("select * from t where n='a  b'", {
      language: 'sql',
      keywordCase: 'upper',
      indent: 2,
      indentStyle: 'standard',
      logicalOperatorNewline: 'before',
      expressionWidth: 80,
      linesBetweenQueries: 2,
    });
    expect(output).toContain("'a  b'");
  });

  it('空输入与语法错误给出中文提示', () => {
    expect(() =>
      formatSql('   ', {
        language: 'sql',
        keywordCase: 'upper',
        indent: 2,
        indentStyle: 'standard',
        logicalOperatorNewline: 'before',
        expressionWidth: 80,
        linesBetweenQueries: 2,
      })
    ).toThrowError('请输入 SQL 内容');

    expect(() =>
      formatSql('select * from where ((', {
        language: 'sql',
        keywordCase: 'upper',
        indent: 2,
        indentStyle: 'standard',
        logicalOperatorNewline: 'before',
        expressionWidth: 80,
        linesBetweenQueries: 2,
      })
    ).toThrowError(/SQL 语法无法解析/);
  });
});

describe('sqlFormatter.compactSql', () => {
  it('折叠空白并去掉逗号前空格', () => {
    expect(compactSql('SELECT\n  a ,\n  b\nFROM t')).toBe('SELECT a, b FROM t');
  });

  it('保留字符串与注释中的原始内容', () => {
    const output = compactSql("select * from t where n = 'a  b' -- keep  it\nand c = 1");
    expect(output).toContain("'a  b'");
    expect(output).toContain('-- keep  it');
  });

  it('函数名与括号之间不留空格', () => {
    expect(compactSql('select count ( * ) from t')).toBe('select count(*) from t');
  });

  it('空输入抛出提示', () => {
    expect(() => compactSql(' \n ')).toThrowError('请输入 SQL 内容');
  });
});

describe('sqlFormatter.normalizeSqlError', () => {
  it('对解析错误补充中文说明', () => {
    expect(normalizeSqlError('Parse error: Expected )')).toContain('SQL 语法无法解析');
  });

  it('其他错误原样返回首行', () => {
    expect(normalizeSqlError('something failed\nsecond line')).toBe('something failed');
  });
});
