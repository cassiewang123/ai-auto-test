import { format } from 'sql-formatter';
import type { KeywordCase, SqlLanguage } from 'sql-formatter';

export type SqlDialect = SqlLanguage;
export type SqlKeywordCase = KeywordCase;
export type SqlIndentStyle = 'standard' | 'tabularLeft' | 'tabularRight';

export interface SqlFormatOptions {
  language: SqlDialect;
  keywordCase: SqlKeywordCase;
  indent: number;
  indentStyle: SqlIndentStyle;
  /** 逻辑运算符（AND/OR）是否换行到新的一行 */
  logicalOperatorNewline: 'before' | 'after';
  /** 每行表达式宽度上限 */
  expressionWidth: number;
  /** 多条语句之间的空行数 */
  linesBetweenQueries: number;
}

export interface SqlDialectOption {
  value: SqlDialect;
  label: string;
  description: string;
}

export const defaultSqlFormatOptions: SqlFormatOptions = {
  language: 'sql',
  keywordCase: 'upper',
  indent: 2,
  indentStyle: 'standard',
  logicalOperatorNewline: 'before',
  expressionWidth: 80,
  linesBetweenQueries: 2,
};

export const sqlDialectOptions: SqlDialectOption[] = [
  { value: 'sql', label: '标准 SQL', description: '通用写法，不确定方言时使用' },
  { value: 'mysql', label: 'MySQL', description: 'MySQL / MariaDB 常用语法' },
  { value: 'plsql', label: 'Oracle PL/SQL', description: 'Oracle 存储过程与匿名块' },
  { value: 'postgresql', label: 'PostgreSQL', description: '支持 ::、RETURNING 等语法' },
  { value: 'transactsql', label: 'SQL Server', description: 'T-SQL，支持 [标识符]' },
  { value: 'hive', label: 'Hive', description: 'Hive SQL' },
  { value: 'spark', label: 'Spark SQL', description: 'Spark SQL' },
  { value: 'bigquery', label: 'BigQuery', description: 'Google BigQuery 标准 SQL' },
  { value: 'snowflake', label: 'Snowflake', description: 'Snowflake SQL' },
  { value: 'sqlite', label: 'SQLite', description: 'SQLite 语法' },
];

/** 格式化 SQL；输入为空或语法无法被解析时抛出可读的中文错误 */
export function formatSql(
  text: string,
  options: SqlFormatOptions = defaultSqlFormatOptions
): string {
  if (text.trim() === '') throw new Error('请输入 SQL 内容');
  try {
    return format(text, {
      language: options.language,
      keywordCase: options.keywordCase,
      tabWidth: options.indent,
      useTabs: false,
      indentStyle: options.indentStyle,
      logicalOperatorNewline: options.logicalOperatorNewline,
      expressionWidth: options.expressionWidth,
      linesBetweenQueries: options.linesBetweenQueries,
    });
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    throw new Error(normalizeSqlError(raw));
  }
}

export function normalizeSqlError(raw: string): string {
  const firstLine = raw.split('\n')[0]?.trim() || 'SQL 解析失败';
  if (/Expected|Unexpected|Parse error/i.test(firstLine)) {
    return `SQL 语法无法解析：${firstLine}。请检查括号、引号是否闭合，或换一个更匹配的方言。`;
  }
  if (/Config/i.test(firstLine)) {
    return `格式化配置不可用：${firstLine}`;
  }
  return firstLine;
}

const openBrackets = '([{';
const closeBrackets = ')]}';
const wordChar = /[\w$]/;

/** 单行压缩：折叠空白、去掉逗号前的空格，同时保留字符串与注释内容 */
export function compactSql(text: string): string {
  if (text.trim() === '') throw new Error('请输入 SQL 内容');

  const source = text.replace(/\r\n?/g, '\n');
  let output = '';
  let index = 0;
  let pendingSpace = false;
  let inLineComment = false;
  let inBlockComment = false;

  const lastChar = () => output[output.length - 1] ?? '';

  while (index < source.length) {
    const char = source[index];
    const next = source[index + 1];

    if (inLineComment) {
      output += char;
      inLineComment = char !== '\n';
      if (!inLineComment) pendingSpace = false;
      index += 1;
      continue;
    }

    if (inBlockComment) {
      output += char;
      if (char === '*' && next === '/') {
        output += next;
        index += 2;
        inBlockComment = false;
        continue;
      }
      index += 1;
      continue;
    }

    if (char === '-' && next === '-') {
      if (pendingSpace && lastChar() !== '' && !openBrackets.includes(lastChar())) output += ' ';
      pendingSpace = false;
      output += '--';
      inLineComment = true;
      index += 2;
      continue;
    }

    if (char === '/' && next === '*') {
      if (pendingSpace && lastChar() !== '' && !openBrackets.includes(lastChar())) output += ' ';
      pendingSpace = false;
      output += '/*';
      inBlockComment = true;
      index += 2;
      continue;
    }

    if (/\s/.test(char)) {
      pendingSpace = true;
      index += 1;
      continue;
    }

    // 引号包裹的内容原样保留，包括其中的空格与换行
    if (char === "'" || char === '"' || char === '`') {
      if (pendingSpace && lastChar() !== '' && !openBrackets.includes(lastChar())) output += ' ';
      pendingSpace = false;
      let cursor = index + 1;
      output += char;
      while (cursor < source.length) {
        const inner = source[cursor];
        output += inner;
        if (inner === '\\' && cursor + 1 < source.length) {
          output += source[cursor + 1];
          cursor += 2;
          continue;
        }
        if (inner === char) {
          if (source[cursor + 1] === char) {
            output += source[cursor + 1];
            cursor += 2;
            continue;
          }
          cursor += 1;
          break;
        }
        cursor += 1;
      }
      index = cursor;
      continue;
    }

    // PostgreSQL 的 $tag$ 字符串
    if (char === '$') {
      const tag = /^\$[A-Za-z_][\w]*\$|^\$\$/.exec(source.slice(index));
      if (tag) {
        if (pendingSpace && lastChar() !== '' && !openBrackets.includes(lastChar())) output += ' ';
        pendingSpace = false;
        const closing = source.indexOf(tag[0], index + tag[0].length);
        const end = closing === -1 ? source.length : closing + tag[0].length;
        output += source.slice(index, end);
        index = end;
        continue;
      }
    }

    if (char === ',') {
      output = `${output.replace(/\s+$/, '')},`;
      pendingSpace = true;
      index += 1;
      continue;
    }

    const previous = lastChar();
    const needsSpace =
      pendingSpace &&
      previous !== '' &&
      !openBrackets.includes(previous) &&
      !closeBrackets.includes(char) &&
      // 函数调用：name( 之间不留空格
      !(char === '(' && wordChar.test(previous));

    if (needsSpace) output += ' ';
    pendingSpace = false;

    if (char === '(' && wordChar.test(previous)) {
      output = output.replace(/\s+$/, '');
    }

    output += char;
    index += 1;
  }

  return output.trim();
}
