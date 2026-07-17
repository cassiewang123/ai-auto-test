import type { ReactNode } from 'react';
import {
  AimOutlined,
  ApartmentOutlined,
  ApiOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  BlockOutlined,
  BookOutlined,
  BugOutlined,
  ClockCircleOutlined,
  CloudOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  EnvironmentOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  GlobalOutlined,
  HistoryOutlined,
  ImportOutlined,
  KeyOutlined,
  LineChartOutlined,
  NotificationOutlined,
  PieChartOutlined,
  ProjectOutlined,
  ReadOutlined,
  RobotOutlined,
  RocketOutlined,
  SafetyOutlined,
  ScheduleOutlined,
  SolutionOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';

export type AppMode = 'lite' | 'full';

export type NavigationItem = {
  key: string;
  icon?: ReactNode;
  label: string;
  children?: NavigationItem[];
  'data-testid'?: string;
};

const navigationItems: NavigationItem[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/jobs', icon: <ThunderboltOutlined />, label: '任务中心' },
  {
    key: 'api-test',
    icon: <ApiOutlined />,
    label: 'API 测试',
    children: [
      { key: '/api-list', icon: <ApiOutlined />, label: '接口定义' },
      { key: '/api-docs', icon: <ReadOutlined />, label: '接口文档' },
      { key: '/quick-test', icon: <ThunderboltOutlined />, label: '接口调试' },
      { key: '/test-cases', icon: <UnorderedListOutlined />, label: '用例管理' },
      { key: '/test-plans', icon: <ScheduleOutlined />, label: '测试计划' },
      { key: '/test-data', icon: <DatabaseOutlined />, label: '数据驱动' },
      { key: '/import', icon: <ImportOutlined />, label: '接口导入' },
      { key: '/mock-service', icon: <BlockOutlined />, label: 'Mock 服务' },
    ],
  },
  {
    key: 'ui-test',
    icon: <DesktopOutlined />,
    label: 'UI 测试',
    children: [
      { key: '/ui-test-cases', icon: <DesktopOutlined />, label: 'UI 用例管理' },
      { key: '/ui-test-suites', icon: <AppstoreOutlined />, label: '测试套件' },
      { key: '/step-library', icon: <ApartmentOutlined />, label: '步骤库' },
      { key: '/ui-elements', icon: <AimOutlined />, label: '元素对象库' },
      { key: '/ui-test-records', icon: <FileSearchOutlined />, label: '调用记录' },
      { key: '/ui-test-logs', icon: <FileTextOutlined />, label: '日志查询' },
    ],
  },
  {
    key: 'perf-test',
    icon: <RocketOutlined />,
    label: '性能测试',
    children: [
      { key: '/perf-tests', icon: <RocketOutlined />, label: '压测场景' },
      { key: '/perf-reports', icon: <LineChartOutlined />, label: '性能报告' },
      { key: '/perf-dashboard', icon: <DashboardOutlined />, label: '实时仪表盘' },
    ],
  },
  { key: '/reports', icon: <BarChartOutlined />, label: '测试报告' },
  { key: '/coverage', icon: <PieChartOutlined />, label: '覆盖率看板' },
  { key: '/quality-gates', icon: <SafetyOutlined />, label: '质量门禁' },
  { key: '/defects', icon: <BugOutlined />, label: '缺陷管理' },
  { key: '/scheduled-tasks', icon: <ClockCircleOutlined />, label: '定时任务' },
  { key: '/environments', icon: <EnvironmentOutlined />, label: '环境管理' },
  { key: '/variables', icon: <GlobalOutlined />, label: '变量管理' },
  { key: '/projects', icon: <ProjectOutlined />, label: '项目管理' },
  { key: '/history', icon: <HistoryOutlined />, label: '历史记录' },
  { key: '/ai', icon: <RobotOutlined />, label: 'AI 助手' },
  { key: '/ai-ops', icon: <RobotOutlined />, label: 'AI 运营' },
  {
    key: 'knowledge',
    icon: <BookOutlined />,
    label: '知识工程',
    children: [
      { key: '/knowledge/defects', icon: <BugOutlined />, label: '缺陷模式库' },
      { key: '/knowledge/rules', icon: <SolutionOutlined />, label: '业务规则库' },
      { key: '/knowledge/interfaces', icon: <ApiOutlined />, label: '接口知识库' },
    ],
  },
  {
    key: 'system',
    icon: <SafetyOutlined />,
    label: '系统管理',
    children: [
      { key: '/users', icon: <TeamOutlined />, label: '用户管理' },
      { key: '/roles', icon: <SafetyOutlined />, label: '角色管理' },
      { key: '/api-tokens', icon: <KeyOutlined />, label: 'API Token' },
      { key: '/ci-cd', icon: <CloudOutlined />, label: 'CI/CD 集成' },
      { key: '/notifications', icon: <NotificationOutlined />, label: '通知管理' },
      { key: '/audit-logs', icon: <FileSearchOutlined />, label: '审计日志' },
    ],
  },
];

const liteRootKeys = new Set([
  '/dashboard',
  '/jobs',
  'api-test',
  'ui-test',
  'perf-test',
  '/reports',
  '/coverage',
  '/scheduled-tasks',
  '/environments',
  '/variables',
  '/projects',
  '/history',
  '/ai',
]);

const withMenuTestIds = (items: NavigationItem[]): NavigationItem[] =>
  items.map((item) => ({
    ...item,
    'data-testid': `menu-${item.key.replace(/^\//, '')}`,
    ...(item.children ? { children: withMenuTestIds(item.children) } : {}),
  }));

export const allNavigationItems = withMenuTestIds(navigationItems);

export const resolveAppMode = (value: string | undefined): AppMode =>
  value?.toLowerCase() === 'full' ? 'full' : 'lite';

export const getNavigationItems = (mode: AppMode): NavigationItem[] =>
  mode === 'full'
    ? allNavigationItems
    : allNavigationItems.filter((item) => liteRootKeys.has(item.key));

export const flattenLeafKeys = (items: NavigationItem[]): string[] =>
  items.flatMap((item) =>
    item.children?.length ? flattenLeafKeys(item.children) : [item.key]
  );

const pathnameMatches = (pathname: string, key: string): boolean =>
  pathname === key || pathname.startsWith(`${key}/`);

export const findNavigationItemByPath = (
  items: NavigationItem[],
  pathname: string
): NavigationItem | undefined => {
  const matchingKeys = flattenLeafKeys(items)
    .filter((key) => pathnameMatches(pathname, key))
    .sort((left, right) => right.length - left.length);
  const selectedKey = matchingKeys[0];

  if (!selectedKey) return undefined;

  for (const item of items) {
    if (item.children?.length) {
      const found = findNavigationItemByPath(item.children, pathname);
      if (found?.key === selectedKey) return found;
    } else if (item.key === selectedKey) {
      return item;
    }
  }

  return undefined;
};

export const getOpenKeys = (
  items: NavigationItem[],
  pathname: string
): string[] => {
  for (const item of items) {
    if (!item.children?.length) continue;
    if (findNavigationItemByPath(item.children, pathname)) {
      return [item.key, ...getOpenKeys(item.children, pathname)];
    }
  }

  return [];
};
