/**
 * 复制文本到剪贴板。
 *
 * 优先使用异步 Clipboard API（需要 https 或 localhost）；
 * 在非安全上下文（例如内网 http 访问）回退到临时 textarea + execCommand。
 *
 * @throws 两种方式都失败时抛出可读错误
 */
export async function copyTextToClipboard(text: string): Promise<void> {
  const value = String(text ?? '');

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  if (typeof document === 'undefined') {
    throw new Error('当前环境不支持剪贴板');
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.top = '-1000px';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  try {
    textarea.select();
    const succeeded = document.execCommand('copy');
    if (!succeeded) {
      throw new Error('复制失败，请手动选择文本复制');
    }
  } finally {
    document.body.removeChild(textarea);
  }
}
