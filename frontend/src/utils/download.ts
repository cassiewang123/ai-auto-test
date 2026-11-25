/**
 * 下载文本内容为本地文件。
 *
 * 统一收口 `Blob + createObjectURL + <a> 点击` 的样板代码，
 * 结束后释放对象 URL，避免内存泄漏。
 *
 * @param filename 下载后的文件名（含扩展名）
 * @param content 文件内容
 * @param mime MIME 类型，默认 `text/plain`
 */
export function downloadTextFile(
  filename: string,
  content: string,
  mime = 'text/plain'
): void {
  if (typeof document === 'undefined') return;

  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default downloadTextFile;
