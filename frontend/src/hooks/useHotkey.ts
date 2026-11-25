import { useEffect, useRef } from 'react';

/** Windows / Linux 用 Ctrl+Enter，macOS 用 Cmd+Enter。 */
export const MOD_ENTER_HINT = 'Ctrl+Enter（macOS 为 Cmd+Enter）';

/** 判断按键事件是否为「修饰键 + Enter」。 */
export function isModEnter(event: KeyboardEvent): boolean {
  return (event.ctrlKey || event.metaKey) && event.key === 'Enter';
}

/**
 * 绑定全局 `Ctrl/Cmd + Enter` 快捷键。
 *
 * - `enabled` 为 false 时不注册监听（例如主操作被禁用时）；
 * - handler 通过 ref 转发，避免每次渲染重新绑定监听；
 * - 命中时阻止默认行为，避免输入框内换行或表单重复提交。
 */
export function useModEnter(handler: () => void, enabled = true): void {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isModEnter(event)) return;
      event.preventDefault();
      handlerRef.current();
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}

export default useModEnter;
