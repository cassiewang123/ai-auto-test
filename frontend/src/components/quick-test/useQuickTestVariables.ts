/**
 * 汇聚接口调试页「当前实际可用变量」的 hook。
 *
 * 来源与优先级（与后端 `_load_direct_execution_context` 的合并顺序一致，
 * 由低到高）：全局/工作区变量 → 当前环境变量 → 本页覆盖。
 *
 * 注意：环境的 `base_url` 只用于「相对 URL 前缀拼接」，不会作为变量参与
 * `{{var}}` 渲染，因此它只展示在面板里（referenceable=false），不进入
 * 输入提示集合 names。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { globalVariableApi } from '../../services/api';
import type { GlobalVariable } from '../../types';

/** 变量来源 */
export type VariableSource = 'page' | 'environment' | 'global';

export const VARIABLE_SOURCE_LABEL: Record<VariableSource, string> = {
  page: '本页覆盖',
  environment: '环境',
  global: '全局/工作区',
};

/** 单个变量条目（含来源、是否被覆盖、是否可用 {{}} 引用） */
export interface VariableEntry {
  name: string;
  /** 展示用字符串值（对象/数字会序列化） */
  value: string;
  source: VariableSource;
  /** 同名变量被更高优先级覆盖时标记为 true */
  overridden: boolean;
  /** 是否可作为 `{{name}}` 变量引用；环境 base_url 为 false */
  referenceable: boolean;
  /** 不可引用时的说明文案 */
  note?: string;
}

/** 环境 base_url 的固定说明（与后端「只做相对 URL 前缀」语义对齐） */
export const BASE_URL_NOTE = '仅用于相对 URL 前缀，不可 {{}} 引用';

export interface QuickTestVariablesOptions {
  /** 当前选中的环境（WorkspaceContext 的 selectedEnvironment） */
  environment?: {
    id?: string;
    name?: string;
    base_url?: string | null;
    variables?: Record<string, unknown>;
  } | null;
  /** 本页「高级设置 → 环境变量」TextArea 的原始 JSON 文本 */
  pageVariablesText: string;
  /** 当前工作区项目（全局变量按「global 或本项目」过滤，与后端一致） */
  projectId?: string | null;
}

export interface QuickTestVariablesResult {
  /** 全部展示条目（含被覆盖、不可引用项），按 全局 → 环境 → 本页 顺序 */
  entries: VariableEntry[];
  /** 可作为 {{name}} 引用的变量名列表（供输入提示；不含环境 base_url） */
  names: string[];
  /** 全局变量加载状态 */
  loading: boolean;
  /** 全局变量加载失败信息（不阻塞页面） */
  error: string | null;
  /** 本页覆盖 JSON 是否非法 */
  pageVariablesValid: boolean;
  /** 重试加载全局变量 */
  reload: () => void;
}

const GLOBAL_VARIABLE_PAGE_SIZE = 200;

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

/** 解析本页覆盖 JSON（非法时返回 null） */
function parsePageOverrides(text: string): Record<string, unknown> | null {
  const trimmed = String(text ?? '').trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function useQuickTestVariables(
  options: QuickTestVariablesOptions
): QuickTestVariablesResult {
  const { environment, pageVariablesText, projectId } = options;
  const [globalVariables, setGlobalVariables] = useState<GlobalVariable[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await globalVariableApi.list({
        page: 1,
        page_size: GLOBAL_VARIABLE_PAGE_SIZE,
      });
      setGlobalVariables((response?.data ?? []) as GlobalVariable[]);
    } catch (loadError: any) {
      setGlobalVariables([]);
      setError(loadError?.message || '全局变量加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const pageOverrides = useMemo(
    () => parsePageOverrides(pageVariablesText),
    [pageVariablesText]
  );
  const pageVariablesValid = pageOverrides !== null;

  return useMemo(() => {
    // 与后端 load_global_variables 一致：global 作用域 +（有项目时）本项目的 workspace 变量
    const globalScopeEntries: VariableEntry[] = globalVariables
      .filter((variable) =>
        variable.scope === 'global'
        || (projectId ? variable.project_id === projectId : false)
      )
      .map((variable) => ({
        name: variable.name,
        value: stringifyValue(variable.value),
        source: 'global',
        overridden: false,
        referenceable: true,
      }));

    const environmentEntries: VariableEntry[] = [];
    if (environment?.base_url) {
      // 仅用于相对 URL 前缀拼接，不是可渲染变量
      environmentEntries.push({
        name: 'base_url',
        value: environment.base_url,
        source: 'environment',
        overridden: false,
        referenceable: false,
        note: BASE_URL_NOTE,
      });
    }
    Object.entries(environment?.variables ?? {}).forEach(([name, value]) => {
      environmentEntries.push({
        name,
        value: stringifyValue(value),
        source: 'environment',
        overridden: false,
        referenceable: true,
      });
    });

    const pageEntries: VariableEntry[] =
      pageOverrides === null
        ? []
        : Object.entries(pageOverrides).map(([name, value]) => ({
            name,
            value: stringifyValue(value),
            source: 'page',
            overridden: false,
            referenceable: true,
          }));

    // 优先级从高到低：page > environment > global；低优先级同名条目标记被覆盖
    const seen = new Set<string>();
    const markOverridden = (list: VariableEntry[]) => {
      list.forEach((entry) => {
        if (seen.has(entry.name)) {
          entry.overridden = true;
        } else {
          seen.add(entry.name);
        }
      });
    };
    markOverridden(pageEntries);
    markOverridden(environmentEntries);
    markOverridden(globalScopeEntries);

    const entries = [...globalScopeEntries, ...environmentEntries, ...pageEntries];
    // 输入提示只给「真正能参与 {{}} 渲染」的名字；环境 base_url 属于展示信息
    const nonReferenceableNames = new Set(
      entries.filter((entry) => !entry.referenceable).map((entry) => entry.name)
    );
    const names = [...seen]
      .filter((name) => !nonReferenceableNames.has(name))
      .sort((a, b) => a.localeCompare(b));

    return {
      entries,
      names,
      loading,
      error,
      pageVariablesValid,
      reload,
    };
  }, [environment, error, globalVariables, loading, pageOverrides, pageVariablesValid, projectId, reload]);
}
