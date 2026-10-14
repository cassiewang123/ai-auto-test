import '@testing-library/jest-dom'

Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
  configurable: true,
  writable: true,
  value: true,
});

const browserGetComputedStyle = window.getComputedStyle.bind(window);
Object.defineProperty(window, 'getComputedStyle', {
  configurable: true,
  value: (element: Element) => browserGetComputedStyle(element),
});

// antd 的 Table/Tabs/Select 依赖这两个浏览器 API，jsdom 未实现
class ResizeObserverShim {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (!('ResizeObserver' in globalThis)) {
  Object.defineProperty(globalThis, 'ResizeObserver', {
    configurable: true,
    writable: true,
    value: ResizeObserverShim,
  });
}

// jsdom 未实现 matchMedia，antd 的响应式组件需要它。
// 默认按桌面视口（md 及以上命中）返回，避免移动端分支让侧边栏菜单不渲染。
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  writable: true,
  value: (query: string) => {
    const minWidth = /min-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
    const maxWidth = /max-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
    const viewportWidth = 1280;
    let matches = true;
    if (minWidth) matches = matches && viewportWidth >= Number(minWidth[1]);
    if (maxWidth) matches = matches && viewportWidth <= Number(maxWidth[1]);
    return {
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  },
});
