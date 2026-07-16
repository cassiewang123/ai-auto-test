import { useState, useEffect, type ReactNode } from 'react';
import { Layout, Menu, theme, ConfigProvider, Space, Avatar, Dropdown } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import {
  LogoutOutlined,
  UserOutlined,
  DashboardOutlined,
  ApiOutlined,
  EnvironmentOutlined,
  ScheduleOutlined,
  BarChartOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  UnorderedListOutlined,
  ImportOutlined,
  ProjectOutlined,
  ClockCircleOutlined,
  BlockOutlined,
  DesktopOutlined,
  AimOutlined,
  AppstoreOutlined,
  RocketOutlined,
  LineChartOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  TeamOutlined,
  SafetyOutlined,
  KeyOutlined,
  CloudOutlined,
  DatabaseOutlined,
  NotificationOutlined,
  BookOutlined,
  BugOutlined,
  SolutionOutlined,
  PieChartOutlined,
  ReadOutlined,
  GlobalOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate, Navigate } from 'react-router-dom';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

dayjs.locale('zh-cn');

const { Header, Sider, Content } = Layout;

// 菜单项类型：支持嵌套 children（对应 antd Menu 的 SubMenu）
type MenuItem = {
  key: string;
  icon?: ReactNode;
  label: string;
  children?: MenuItem[];
  'data-testid'?: string;
};

const menuItems: MenuItem[] = [
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

// 根据当前路径计算需要展开的 SubMenu key
const getOpenKeys = (pathname: string): string[] => {
  if (
    ['/api-list', '/api-docs', '/quick-test', '/test-cases', '/test-plans', '/test-data', '/import', '/mock-service'].some((p) =>
      pathname.startsWith(p)
    )
  ) {
    return ['api-test'];
  }
  if (['/ui-test-cases', '/ui-test-suites', '/step-library', '/ui-elements', '/ui-test-records', '/ui-test-logs'].some((p) => pathname.startsWith(p))) {
    return ['ui-test'];
  }
  if (['/perf-tests', '/perf-reports', '/perf-dashboard'].some((p) => pathname.startsWith(p))) {
    return ['perf-test'];
  }
  if (['/knowledge/defects', '/knowledge/rules', '/knowledge/interfaces'].some((p) => pathname.startsWith(p))) {
    return ['knowledge'];
  }
  if (['/users', '/roles', '/api-tokens', '/ci-cd', '/notifications'].some((p) => pathname.startsWith(p))) {
    return ['system'];
  }
  return [];
};

// 递归收集所有叶子菜单项 key
const flattenLeafKeys = (items: MenuItem[]): string[] =>
  items.flatMap((item) => (item.children?.length ? flattenLeafKeys(item.children) : [item.key]));

// 递归查找指定 key 的叶子菜单项
const findLeafItem = (items: MenuItem[], key: string): MenuItem | undefined => {
  for (const item of items) {
    if (item.children?.length) {
      const found = findLeafItem(item.children, key);
      if (found) return found;
    } else if (item.key === key) {
      return item;
    }
  }
  return undefined;
};

// 为每个菜单项注入 data-testid（基于 key 去掉前导 /，例如 /dashboard -> menu-dashboard）
const withMenuTestIds = (items: MenuItem[]): MenuItem[] =>
  items.map((item) => ({
    ...item,
    'data-testid': `menu-${item.key.replace(/^\//, '')}`,
    ...(item.children ? { children: withMenuTestIds(item.children) } : {}),
  }));

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { token: themeToken } = theme.useToken();
  const { user, logout, loading } = useAuth();
  const [openKeys, setOpenKeys] = useState<string[]>(() => getOpenKeys(location.pathname));

  // 路径变化时，确保对应 SubMenu 展开（保留用户已展开的其他 SubMenu）
  // 注意：所有 hooks 必须在条件 return 之前调用，否则违反 React Hooks 规则
  useEffect(() => {
    const pathOpen = getOpenKeys(location.pathname);
    setOpenKeys((prev) => {
      const merged = new Set(prev);
      pathOpen.forEach((k) => merged.add(k));
      return Array.from(merged);
    });
  }, [location.pathname]);

  // 认证守卫：加载中显示空白，加载完成且未登录才跳转
  if (loading) return null;
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const selectedKey =
    flattenLeafKeys(menuItems).find((k) => location.pathname.startsWith(k)) || '/dashboard';

  const selectedItem = findLeafItem(menuItems, selectedKey);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#4f46e5',
          colorSuccess: '#059669',
          colorWarning: '#d97706',
          colorError: '#dc2626',
          colorInfo: '#0891b2',
          borderRadius: 8,
          fontSize: 14,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
        components: {
          Menu: {
            darkItemBg: '#0f172a',
            darkSubMenuItemBg: '#0f172a',
            darkItemSelectedBg: '#1e293b',
            darkItemHoverBg: '#1e293b',
            darkItemHoverColor: '#e2e8f0',
          },
          Card: {
            colorBorderSecondary: '#e5e7eb',
            borderRadiusLG: 12,
          },
          Table: {
            headerBg: '#f9fafb',
            headerColor: '#6b7280',
            rowHoverBg: '#f9fafb',
            borderColor: '#f3f4f6',
          },
          Tag: {
            defaultBg: '#f3f4f6',
            borderRadiusSM: 6,
          },
          Button: {
            borderRadius: 8,
          },
        },
      }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          style={{
            overflow: 'auto',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            bottom: 0,
          }}
        >
          <div
            style={{
              height: 48,
              margin: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: collapsed ? 16 : 15,
              fontWeight: 700,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            }}
          >
            {collapsed ? 'AI' : 'AI 测试平台'}
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            openKeys={openKeys}
            onOpenChange={(keys) => setOpenKeys(keys)}
            items={withMenuTestIds(menuItems)}
            onClick={({ key }) => navigate(key)}
            data-testid="sidebar-menu"
          />
        </Sider>
        <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'all 0.2s' }}>
          <Header
            style={{
              padding: '0 24px',
              background: themeToken.colorBgContainer,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
              position: 'sticky',
              top: 0,
              zIndex: 10,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 600 }}>
              {selectedItem?.label}
            </span>
            <Space size="large" align="center">
              <span style={{ color: '#6b7280', fontSize: 13 }}>
                {dayjs().format('YYYY-MM-DD dddd')}
              </span>
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'logout',
                      icon: <LogoutOutlined />,
                      label: '退出登录',
                      'data-testid': 'logout-btn',
                    },
                  ],
                  onClick: ({ key }) => {
                    if (key === 'logout') {
                      logout();
                      navigate('/login', { replace: true });
                    }
                  },
                }}
                placement="bottomRight"
              >
                <Space style={{ cursor: 'pointer' }} data-testid="user-dropdown">
                  <Avatar
                    size="small"
                    icon={<UserOutlined />}
                    style={{ backgroundColor: '#4f46e5' }}
                  />
                  <span style={{ fontSize: 14 }}>
                    {user.username}
                    {user.is_superuser && (
                      <span style={{ color: '#4f46e5', marginLeft: 4, fontSize: 12 }}>
                        (管理员)
                      </span>
                    )}
                  </span>
                </Space>
              </Dropdown>
            </Space>
          </Header>
          <Content
            style={{
              margin: 24,
              padding: 24,
              background: '#f9fafb',
              borderRadius: 12,
              minHeight: 280,
            }}
          >
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}
