import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  allNavigationItems,
  findNavigationItemByPath,
} from '../components/navigation';
import type { KeepAliveHandle } from '../components/KeepAliveOutlet';

export interface PageTab {
  /** 路由路径，同时作为 Tab 的身份标识 */
  path: string;
  label: string;
}

interface PageTabsContextValue {
  tabs: PageTab[];
  activeKey: string;
  openTab: (path: string, label?: string) => void;
  selectTab: (path: string) => void;
  closeTab: (path: string) => void;
  closeOtherTabs: (path: string) => void;
  closeAllTabs: () => void;
  /** 重新挂载某个标签对应的页面（清除缓存后重新加载） */
  refreshTab: (path: string) => void;
  /** 供保活容器注册页面缓存回调 */
  keepAliveRef: RefObject<KeepAliveHandle | null>;
}

const DEFAULT_HOME: PageTab = { path: '/dashboard', label: '仪表盘' };
const STORAGE_KEY = 'airetest.page-tabs';

/** 跨渲染保持同一个 ref 对象，避免保活容器因 ref 变化重复注册 */
const sharedKeepAliveRef: RefObject<KeepAliveHandle | null> = { current: null };

const PageTabsContext = createContext<PageTabsContextValue | null>(null);

/** 把路径解析成菜单里的中文名称；非菜单路由（如登录页）返回 null */
export function resolveTabLabel(path: string): string | null {
  const item = findNavigationItemByPath(allNavigationItems, path);
  return item?.label ?? null;
}

function loadStoredTabs(): PageTab[] {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is PageTab =>
          !!item &&
          typeof (item as PageTab).path === 'string' &&
          typeof (item as PageTab).label === 'string'
      )
      .map((item) => ({ path: item.path, label: item.label }));
  } catch {
    return [];
  }
}

export function PageTabsProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [tabs, setTabs] = useState<PageTab[]>(loadStoredTabs);
  const keepAliveRef = useRef<KeepAliveHandle | null>(sharedKeepAliveRef.current);
  const pathname = location.pathname;
  // 记住当前打开路径，关闭 Tab 时用它判断是否需要跳转
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;

  // 当前路由始终对应一个 Tab：菜单跳转、页面内 Link、直接输入地址都会落到这里
  useEffect(() => {
    const label = resolveTabLabel(pathname);
    if (!label) return; // 登录页等非平台页面不建标签
    setTabs((prev) => {
      if (prev.some((tab) => tab.path === pathname)) return prev;
      return [...prev, { path: pathname, label }];
    });
  }, [pathname]);

  // 刷新页面后恢复已打开的标签
  useEffect(() => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
    } catch {
      // 存储不可用时忽略，标签功能不依赖它
    }
  }, [tabs]);

  // 最后一个 Tab 关闭后不能停在空白页
  useEffect(() => {
    if (tabs.length === 0) {
      navigate(DEFAULT_HOME.path, { replace: true });
    }
  }, [tabs.length, navigate]);

  const openTab = useCallback((path: string, label?: string) => {
    const resolved = label || resolveTabLabel(path);
    if (!resolved) return;
    setTabs((prev) => {
      if (prev.some((tab) => tab.path === path)) return prev;
      return [...prev, { path, label: resolved }];
    });
  }, []);

  const selectTab = useCallback(
    (path: string) => {
      if (path !== pathnameRef.current) navigate(path);
    },
    [navigate]
  );

  const closeTab = useCallback(
    (path: string) => {
      keepAliveRef.current?.removePage(path);
      setTabs((prev) => {
        const index = prev.findIndex((tab) => tab.path === path);
        if (index === -1) return prev;
        const next = prev.filter((tab) => tab.path !== path);
        if (path === pathnameRef.current && next.length > 0) {
          // 关掉当前页时，优先回到左侧相邻 Tab，否则回到新的第一个 Tab
          const neighbour = next[index - 1] ?? next[0];
          navigate(neighbour.path);
        }
        return next;
      });
    },
    [navigate]
  );

  const closeOtherTabs = useCallback(
    (path: string) => {
      setTabs((prev) => {
        prev
          .filter((tab) => tab.path !== path)
          .forEach((tab) => keepAliveRef.current?.removePage(tab.path));
        const keep = prev.filter((tab) => tab.path === path);
        if (keep.length === 0) return prev;
        if (path !== pathnameRef.current) navigate(path);
        return keep;
      });
    },
    [navigate]
  );

  const closeAllTabs = useCallback(() => {
    setTabs((prev) => {
      prev.forEach((tab) => keepAliveRef.current?.removePage(tab.path));
      return [];
    });
  }, []);

  const refreshTab = useCallback((path: string) => {
    keepAliveRef.current?.refreshPage(path);
  }, []);

  const value = useMemo<PageTabsContextValue>(
    () => ({
      tabs,
      activeKey: pathname,
      openTab,
      selectTab,
      closeTab,
      closeOtherTabs,
      closeAllTabs,
      refreshTab,
      keepAliveRef: keepAliveRef as RefObject<KeepAliveHandle | null>,
    }),
    [
      tabs,
      pathname,
      openTab,
      selectTab,
      closeTab,
      closeOtherTabs,
      closeAllTabs,
      refreshTab,
    ]
  );

  return <PageTabsContext.Provider value={value}>{children}</PageTabsContext.Provider>;
}

export function usePageTabs(): PageTabsContextValue {
  const context = useContext(PageTabsContext);
  if (!context) {
    throw new Error('usePageTabs 必须在 PageTabsProvider 内使用');
  }
  return context;
}

export { DEFAULT_HOME };
