import {
  BgColorsOutlined,
  CodeOutlined,
  DiffOutlined,
  FileSearchOutlined,
  FieldTimeOutlined,
  FileTextOutlined,
  FontSizeOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';

export type ToolIconKey =
  | 'json'
  | 'text'
  | 'regex'
  | 'encoding'
  | 'word'
  | 'time'
  | 'data'
  | 'log';

export interface ToolDefinition {
  id: string;
  path: string;
  name: string;
  description: string;
  icon: ToolIconKey;
}

export const toolDefinitions: ToolDefinition[] = [
  {
    id: 'json-compare',
    path: '/tools/json-compare',
    name: 'JSON 数据对比',
    description: '按路径比较两份 JSON，识别新增、删除、修改和类型变化。',
    icon: 'json',
  },
  {
    id: 'text-compare',
    path: '/tools/text-compare',
    name: '文本对比',
    description: '逐行比较两段文本，标出新增、删除和相同内容。',
    icon: 'text',
  },
  {
    id: 'regex-tester',
    path: '/tools/regex',
    name: '正则测试',
    description: '实时测试正则表达式，查看匹配位置、分组和替换结果。',
    icon: 'regex',
  },
  {
    id: 'encoding',
    path: '/tools/encoding',
    name: '编码转换',
    description: 'Base64、URL、Hex、Unicode 和 HTML 实体互转。',
    icon: 'encoding',
  },
  {
    id: 'word-count',
    path: '/tools/word-count',
    name: '字数统计',
    description: '统计字符、单词、中文字符、行数、段落和高频词。',
    icon: 'word',
  },
  {
    id: 'timestamp',
    path: '/tools/timestamp',
    name: '时间处理',
    description: '日期与秒级、毫秒级时间戳互转，查看当前时间。',
    icon: 'time',
  },
  {
    id: 'data-generator',
    path: '/tools/data-generator',
    name: '测试数据生成',
    description: '生成姓名、邮箱、手机号、IP、地址、UUID 等测试数据。',
    icon: 'data',
  },
  {
    id: 'log-analysis',
    path: '/tools/log-analysis',
    name: '日志分析',
    description: '解析日志级别和时间，统计错误率并按条件过滤。',
    icon: 'log',
  },
];

export const toolIcons: Record<ToolIconKey, ReactNode> = {
  json: <DiffOutlined />,
  text: <SwapOutlined />,
  regex: <CodeOutlined />,
  encoding: <BgColorsOutlined />,
  word: <FontSizeOutlined />,
  time: <FieldTimeOutlined />,
  data: <FileTextOutlined />,
  log: <FileSearchOutlined />,
};

export const toolNavChildren = toolDefinitions.map((tool) => ({
  key: tool.path,
  icon: toolIcons[tool.icon],
  label: tool.name,
}));
