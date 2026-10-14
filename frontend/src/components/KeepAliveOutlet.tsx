import { useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { matchRoutes, useLocation, Outlet, UNSAFE_RouteContext } from 'react-router-dom';
import { routeObjects } from '../routes';

/**
 * 缓存上限只是兜底：正常打开的页面由标签页负责回收（关闭标签时调用 removePage）。
 * 超出上限时按最久未访问的顺序回收，但始终保留当前显示的页面。
 */
const KEEP_ALIVE_LIMIT = 12;

export interface KeepAliveRoute {
  path?: string;
  element?: ReactNode;
  children?: KeepAliveRoute[];
}

/**
 * 保活容器需要与当前 <Routes> 使用同一份路由表才能找到页面元素。
 * 默认 lazy 取全局路由表：routes.tsx 会经 AppLayout 反向引用本模块，
 * 若在模块顶层直接读取会命中循环依赖的暂时性死区。
 * 测试可以通过 setKeepAliveRoutes 注入自己的路由表。
 */
let keepAliveRoutes: KeepAliveRoute[] | null = null;

function currentRoutes(): KeepAliveRoute[] {
  if (keepAliveRoutes) return keepAliveRoutes;
  return routeObjects as unknown as KeepAliveRoute[];
}

export function setKeepAliveRoutes(routes: KeepAliveRoute[]): void {
  keepAliveRoutes = routes;
}

export function resetKeepAliveRoutes(): void {
  keepAliveRoutes = null;
}

export interface KeepAliveHandle {
  removePage: (key: string) => void;
  refreshPage: (key: string) => void;
  refreshActivePage: () => void;
}

interface CacheEntry {
  element: ReactNode;
  context: unknown;
  token: number;
}

/**
 * 标签页保活容器：当前路由对应的页面渲染一次后保留在 DOM 中，
 * 切换标签只是显示/隐藏，组件不卸载、不重新请求数据。
 */
export default function KeepAliveOutlet({ handleRef }: { handleRef?: { current: KeepAliveHandle | null } }) {
  const location = useLocation();
  const parentContext = useContext(UNSAFE_RouteContext);
  const cacheRef = useRef<Map<string, CacheEntry>>(new Map());
  const [refreshTokens, setRefreshTokens] = useState<Record<string, number>>({});
  const pathname = location.pathname;

  const branch = useMemo(() => {
    const matched = matchRoutes(currentRoutes(), location);
    // 取父级路由（带 Outlet 的布局路由）之下的第一个匹配，即当前页面
    const page = matched?.[Math.max(matched.length - 2, 1)];
    if (!page?.route.element) return null;
    return {
      element: page.route.element,
      context: (page as { routeContext?: unknown }).routeContext,
    };
  }, [location]);

  if (branch) {
    const cached = cacheRef.current.get(pathname);
    if (!cached || cached.token !== (refreshTokens[pathname] ?? 0)) {
      cacheRef.current.set(pathname, {
        element: branch.element,
        context: branch.context,
        token: refreshTokens[pathname] ?? 0,
      });
    }
  }

  // 回收超出上限且非当前页的缓存
  const entries = Array.from(cacheRef.current.entries());
  if (entries.length > KEEP_ALIVE_LIMIT) {
    for (const [key] of entries) {
      if (cacheRef.current.size <= KEEP_ALIVE_LIMIT) break;
      if (key === pathname) continue;
      cacheRef.current.delete(key);
    }
  }

  useEffect(() => {
    if (!handleRef) return;
    handleRef.current = {
      removePage(key: string) {
        cacheRef.current.delete(key);
        setRefreshTokens((prev) => {
          if (!(key in prev)) return prev;
          const next = { ...prev };
          delete next[key];
          return next;
        });
      },
      refreshPage(key: string) {
        cacheRef.current.delete(key);
        setRefreshTokens((prev) => ({ ...prev, [key]: (prev[key] ?? 0) + 1 }));
      },
      refreshActivePage() {
        const key = pathname;
        cacheRef.current.delete(key);
        setRefreshTokens((prev) => ({ ...prev, [key]: (prev[key] ?? 0) + 1 }));
      },
    };
    return () => {
      if (handleRef) handleRef.current = null;
    };
  }, [handleRef, pathname]);

  // 没有任何页面被缓存（例如详情类路由）时退回普通 Outlet
  if (cacheRef.current.size === 0) {
    return <Outlet />;
  }

  return (
    <>
      {Array.from(cacheRef.current.entries()).map(([key, entry]) => {
        const active = key === pathname;
        return (
          <div
            key={`${key}#${entry.token}`}
            data-keep-alive-page={key}
            data-active={active ? 'true' : 'false'}
            style={{ display: active ? 'block' : 'none' }}
          >
            {entry.context ? (
              <UNSAFE_RouteContext.Provider value={entry.context as never}>
                {entry.element}
              </UNSAFE_RouteContext.Provider>
            ) : (
              entry.element
            )}
          </div>
        );
      })}
      {!branch && parentContext ? <Outlet /> : null}
    </>
  );
}
