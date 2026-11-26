/**
 * 可上传文档的扩展名清单.
 *
 * 与后端 `requirement_document_parser.SUPPORTED_EXTENSIONS` 保持一致。
 * 前端用它设置 <input accept>，避免「后端能解析但选不到文件」或反之。
 *
 * 注意：accept 只是浏览器的初筛，用户仍可选择「所有文件」；
 * 真正的校验在后端，无法解析的格式会返回明确告警而不是静默失败。
 */

/** 扩展名（不含点），与后端支持列表对齐 */
export const SUPPORTED_DOCUMENT_EXTENSIONS = [
  // 文档
  'pdf',
  'doc',
  'docx',
  'odt',
  'ods',
  'odp',
  'rtf',
  // 表格
  'xls',
  'xlsx',
  'xlsm',
  'csv',
  // 图片（页面原型等）
  'png',
  'jpg',
  'jpeg',
  'webp',
  'bmp',
  'gif',
  'tif',
  'tiff',
  // 纯文本与结构化
  'md',
  'markdown',
  'txt',
  'log',
  'json',
  'yaml',
  'yml',
  'xml',
  'html',
  'htm',
  'ini',
  'conf',
  'sql',
  'properties',
] as const;

/** 可直接用于 <input accept> / antd Upload accept 的字符串 */
export const DOCUMENT_ACCEPT_PATTERN = SUPPORTED_DOCUMENT_EXTENSIONS.map(
  (ext) => `.${ext}`
).join(',');

/** 给用户看的一句话说明 */
export const DOCUMENT_SUPPORT_HINT =
  '支持 PDF、Word、Excel、OpenDocument、纯文本、HTML、图片等常见格式，单文件 <20MB';
