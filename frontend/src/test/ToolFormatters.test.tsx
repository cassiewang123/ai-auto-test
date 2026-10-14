import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import JsonFormatterPage from '../pages/tools/JsonFormatterPage';
import SqlFormatterPage from '../pages/tools/SqlFormatterPage';
import { toolDefinitions, toolNavChildren } from '../pages/tools/toolCatalog';

function setTextareaValue(element: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    'value'
  )?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

describe('工具集：JSON / SQL 格式化', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    window.localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.localStorage.clear();
  });

  function renderPage(node: React.ReactNode) {
    act(() => {
      root.render(<MemoryRouter initialEntries={['/tools']}>{node}</MemoryRouter>);
    });
  }

  it('工具集目录注册了 JSON 格式化与 SQL 格式化，且菜单同步', () => {
    const jsonTool = toolDefinitions.find((tool) => tool.path === '/tools/json-format');
    const sqlTool = toolDefinitions.find((tool) => tool.path === '/tools/sql-format');

    expect(jsonTool?.name).toBe('JSON 格式化');
    expect(sqlTool?.name).toBe('SQL 格式化');
    expect(toolNavChildren.map((item) => item.key)).toContain('/tools/json-format');
    expect(toolNavChildren.map((item) => item.key)).toContain('/tools/sql-format');
  });

  it('JSON 格式化：输入后实时美化并显示统计信息', () => {
    renderPage(<JsonFormatterPage />);

    const input = container.querySelector<HTMLTextAreaElement>(
      '[data-testid="json-input"]'
    )!;
    act(() => setTextareaValue(input, '{"b":1,"a":[1,2]}'));

    const output = container.querySelector<HTMLTextAreaElement>(
      '[data-testid="json-output"]'
    )!;
    expect(output.value).toBe(['{', '  "b": 1,', '  "a": [', '    1,', '    2', '  ]', '}'].join('\n'));
    expect(container.querySelector('[data-testid="json-stats-type"]')?.textContent).toContain(
      '对象'
    );
  });

  it('JSON 格式化：非法输入展示错误提示而不是结果', () => {
    renderPage(<JsonFormatterPage />);

    const input = container.querySelector<HTMLTextAreaElement>(
      '[data-testid="json-input"]'
    )!;
    act(() => setTextareaValue(input, '{"a":1,}'));

    expect(container.querySelector('[data-testid="json-error"]')).not.toBeNull();
    expect(
      container.querySelector<HTMLTextAreaElement>('[data-testid="json-output"]')!.value
    ).toBe('');
  });

  it('SQL 格式化：点击格式化后输出美化结果', () => {
    renderPage(<SqlFormatterPage />);

    const input = container.querySelector<HTMLTextAreaElement>(
      '[data-testid="sql-input"]'
    )!;
    act(() => setTextareaValue(input, 'select id,name from users where id=1'));

    const formatButton = container.querySelector<HTMLElement>(
      '[data-testid="sql-format"]'
    )!;
    act(() => {
      formatButton.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const output = container.querySelector<HTMLTextAreaElement>(
      '[data-testid="sql-output"]'
    )!;
    expect(output.value).toContain('SELECT');
    expect(output.value).toContain('\n  id,');
    expect(output.value).toContain('FROM');
    expect(container.querySelector('[data-testid="sql-error"]')).toBeNull();
  });

  it('SQL 格式化：点击压缩输出单行结果', () => {
    renderPage(<SqlFormatterPage />);

    const input = container.querySelector<HTMLTextAreaElement>(
      '[data-testid="sql-input"]'
    )!;
    act(() => setTextareaValue(input, 'SELECT\n  a ,\n  b\nFROM t'));

    const compactButton = container.querySelector<HTMLElement>(
      '[data-testid="sql-compact"]'
    )!;
    act(() => {
      compactButton.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(
      container.querySelector<HTMLTextAreaElement>('[data-testid="sql-output"]')!.value
    ).toBe('SELECT a, b FROM t');
  });
});
