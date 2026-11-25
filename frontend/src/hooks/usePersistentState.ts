import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';

/** 判断是否为「普通对象」（排除数组、null 与 class 实例）。 */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null) return false;
  if (Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value) as unknown;
  return prototype === Object.prototype || prototype === null;
}

/**
 * 把已保存的数据合并到默认值上。
 *
 * - 标量/数组：已保存值优先；
 * - 普通对象：逐层合并，保证后续新增的默认字段不会因为历史数据而缺失；
 * - 已保存值为空：直接返回默认值。
 */
function mergeWithDefaults<T>(defaults: T, stored: unknown): T {
  if (stored === undefined || stored === null) return defaults;
  if (!isPlainObject(defaults)) return stored as T;
  if (!isPlainObject(stored)) return defaults;

  const merged: Record<string, unknown> = { ...defaults };
  for (const [key, value] of Object.entries(stored)) {
    merged[key] = mergeWithDefaults(defaults[key], value);
  }
  return merged as T;
}

/** 从 localStorage 读取并合并默认值；任何异常都退回默认值。 */
function readStoredValue<T>(key: string, initial: T): T {
  if (typeof window === 'undefined') return initial;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return initial;
    return mergeWithDefaults(initial, JSON.parse(raw) as unknown);
  } catch {
    return initial;
  }
}

function writeStoredValue<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 本地存储不可用（隐私模式 / 超额）时静默降级为内存态
  }
}

/**
 * 与 `useState` 用法一致、但会自动写入 localStorage 的状态。
 *
 * - 首次渲染读取并合并默认值，解析失败自动回退；
 * - 值变化后同步写回，写入失败不影响页面运行。
 */
export function usePersistentState<T>(
  key: string,
  initial: T
): [T, Dispatch<SetStateAction<T>>] {
  const initialRef = useRef(initial);
  const [value, setValue] = useState<T>(() => readStoredValue(key, initialRef.current));

  useEffect(() => {
    writeStoredValue(key, value);
  }, [key, value]);

  const setPersistentValue = useCallback<Dispatch<SetStateAction<T>>>(
    (next) => setValue(next),
    []
  );

  return [value, setPersistentValue];
}

export default usePersistentState;
