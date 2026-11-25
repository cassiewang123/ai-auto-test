import { useCallback } from 'react';
import { message } from 'antd';
import { copyTextToClipboard } from '../utils/clipboard';

/**
 * 复制结果提示文案。默认值保证绝大多数场景零配置可用；
 * 各工具页可传入原有文案以保持提示一致。
 */
export interface CopyFeedback {
  /** 复制成功后的提示，默认「已复制」。 */
  successMessage?: string;
  /** 复制失败后的提示，默认「复制失败」。 */
  errorMessage?: string;
}

/**
 * 剪贴板复制的统一封装。
 *
 * 底层复用 `utils/clipboard` 的 `copyTextToClipboard`（非安全上下文会回退到
 * execCommand，内网 http 访问也能复制），本 Hook 只负责提示与异常收口，
 * 调用方只需关心复制是否成功：
 * ```tsx
 * const { copy } = useCopyToClipboard();
 * await copy(output);
 * ```
 */
export function useCopyToClipboard(): {
  copy: (text: string, feedback?: CopyFeedback) => Promise<boolean>;
} {
  const copy = useCallback(
    async (text: string, feedback: CopyFeedback = {}): Promise<boolean> => {
      const {
        successMessage = '已复制',
        errorMessage = '复制失败',
      } = feedback;
      try {
        await copyTextToClipboard(text);
        message.success(successMessage);
        return true;
      } catch {
        message.error(errorMessage);
        return false;
      }
    },
    []
  );

  return { copy };
}

export default useCopyToClipboard;
