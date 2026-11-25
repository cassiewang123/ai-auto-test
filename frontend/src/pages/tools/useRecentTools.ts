import { useCallback, useMemo } from 'react';
import { usePersistentState } from '../../hooks/usePersistentState';

/** 最近使用记录在 localStorage 中的键名。 */
export const RECENT_TOOLS_STORAGE_KEY = 'airetest.tools.recent';

/** 最近使用最多保留的条数。 */
export const MAX_RECENT_TOOLS = 6;

export interface RecentToolEntry {
  /** 工具 id，对应 ToolDefinition.id。 */
  id: string;
  /** 使用时间戳（毫秒）。 */
  ts: number;
}

function isRecentEntry(value: unknown): value is RecentToolEntry {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<RecentToolEntry>;
  return typeof candidate.id === 'string' && typeof candidate.ts === 'number';
}

/**
 * 「最近使用」工具记录：按使用时间倒序，最多保留 6 条，自动持久化。
 */
export function useRecentTools(): {
  recent: RecentToolEntry[];
  record: (id: string) => void;
  clear: () => void;
} {
  const [stored, setStored] = usePersistentState<RecentToolEntry[]>(
    RECENT_TOOLS_STORAGE_KEY,
    []
  );

  const recent = useMemo(() => {
    const valid = stored.filter(isRecentEntry);
    return [...valid].sort((left, right) => right.ts - left.ts).slice(0, MAX_RECENT_TOOLS);
  }, [stored]);

  const record = useCallback(
    (id: string) => {
      if (!id) return;
      const entry: RecentToolEntry = { id, ts: Date.now() };
      setStored((previous) => {
        const kept = previous.filter(isRecentEntry).filter((item) => item.id !== id);
        return [entry, ...kept].slice(0, MAX_RECENT_TOOLS);
      });
    },
    [setStored]
  );

  const clear = useCallback(() => setStored([]), [setStored]);

  return { recent, record, clear };
}

export default useRecentTools;
