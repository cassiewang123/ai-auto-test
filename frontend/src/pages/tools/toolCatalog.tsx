import {
  BgColorsOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DiffOutlined,
  FileSearchOutlined,
  FieldTimeOutlined,
  FileTextOutlined,
  FontSizeOutlined,
  FormatPainterOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';

export type ToolIconKey =
  | 'json'
  | 'json-format'
  | 'sql'
  | 'text'
  | 'regex'
  | 'encoding'
  | 'word'
  | 'time'
  | 'data'
  | 'log'
  | 'server';

/** 工具分类：用于工具集首页的分组筛选。 */
export type ToolCategory = 'json' | 'text' | 'dev' | 'network';

export interface ToolDefinition {
  id: string;
  path: string;
  name: string;
  description: string;
  icon: ToolIconKey;
  category: ToolCategory;
  // 安全分组：local = 本机处理 · 不外发；high-risk = 高风险 · 默认关闭
  safety: 'local' | 'high-risk';
}

/** 分类展示元数据，顺序即首页筛选器的展示顺序。 */
export const toolCategoryOptions: Array<{ value: ToolCategory; label: string }> = [
  { value: 'json', label: 'JSON' },
  { value: 'text', label: '文本' },
  { value: 'dev', label: '开发' },
  { value: 'network', label: '服务器' },
];

export const toolDefinitions: ToolDefinition[] = [
  {
    id: 'json-compare',
    path: '/tools/json-compare',
    name: 'JSON 数据对比',
    description: '按路径比较两份 JSON，识别新增、删除、修改和类型变化。',
    icon: 'json',
    category: 'json',
    safety: 'local',
  },
  {
    id: 'json-format',
    path: '/tools/json-format',
    name: 'JSON 格式化',
    description: '美化、压缩、按 key 排序和 Unicode 转义 JSON，实时提示语法错误位置。',
    icon: 'json-format',
    category: 'json',
    safety: 'local',
  },
  {
    id: 'sql-format',
    path: '/tools/sql-format',
    name: 'SQL 格式化',
    description: '美化或压缩 SQL，支持 Oracle、MySQL、PostgreSQL、Hive 等方言。',
    icon: 'sql',
    category: 'dev',
    safety: 'local',
  },
  {
    id: 'text-compare',
    path: '/tools/text-compare',
    name: '文本对比',
    description: '逐行比较两段文本，标出新增、删除和相同内容。',
    icon: 'text',
    category: 'text',
    safety: 'local',
  },
  {
    id: 'regex-tester',
    path: '/tools/regex',
    name: '正则测试',
    description: '实时测试正则表达式，查看匹配位置、分组和替换结果。',
    icon: 'regex',
    category: 'text',
    safety: 'local',
  },
  {
    id: 'encoding',
    path: '/tools/encoding',
    name: '编码转换',
    description: 'Base64、URL、Hex、Unicode 和 HTML 实体互转。',
    icon: 'encoding',
    category: 'dev',
    safety: 'local',
  },
  {
    id: 'word-count',
    path: '/tools/word-count',
    name: '字数统计',
    description: '统计字符、单词、中文字符、行数、段落和高频词。',
    icon: 'word',
    category: 'text',
    safety: 'local',
  },
  {
    id: 'timestamp',
    path: '/tools/timestamp',
    name: '时间处理',
    description: '日期与秒级、毫秒级时间戳互转，查看当前时间。',
    icon: 'time',
    category: 'dev',
    safety: 'local',
  },
  {
    id: 'data-generator',
    path: '/tools/data-generator',
    name: '测试数据生成',
    description: '生成姓名、邮箱、手机号、IP、地址、UUID 等测试数据。',
    icon: 'data',
    category: 'dev',
    safety: 'local',
  },
  {
    id: 'log-analysis',
    path: '/tools/log-analysis',
    name: '日志分析',
    description: '解析日志级别和时间，统计错误率并按条件过滤。',
    icon: 'log',
    category: 'dev',
    safety: 'local',
  },
  {
    id: 'server-console',
    path: '/tools/server-console',
    name: '服务器连接',
    description: 'SSH 连接远程服务器，执行 curl 并下载返回数据。',
    icon: 'server',
    category: 'network',
    safety: 'high-risk',
  },
];

export const toolIcons: Record<ToolIconKey, ReactNode> = {
  json: <DiffOutlined />,
  'json-format': <FormatPainterOutlined />,
  sql: <DatabaseOutlined />,
  text: <SwapOutlined />,
  regex: <CodeOutlined />,
  encoding: <BgColorsOutlined />,
  word: <FontSizeOutlined />,
  time: <FieldTimeOutlined />,
  data: <FileTextOutlined />,
  log: <FileSearchOutlined />,
  server: <CloudServerOutlined />,
};

export const toolNavChildren = toolDefinitions.map((tool) => ({
  key: tool.path,
  icon: toolIcons[tool.icon],
  label: tool.name,
}));
