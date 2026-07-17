import { useState, useEffect } from 'react';
import {
  Avatar,
  Button,
  ConfigProvider,
  Drawer,
  Dropdown,
  Grid,
  Layout,
  Menu,
  Space,
  theme,
} from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { LogoutOutlined, MenuOutlined, UserOutlined } from '@ant-design/icons';
import { Outlet, useLocation, useNavigate, Navigate } from 'react-router-dom';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import {
  allNavigationItems,
  findNavigationItemByPath,
  getNavigationItems,
  getOpenKeys,
  resolveAppMode,
} from './navigation';

dayjs.locale('zh-cn');

const { Header, Sider, Content } = Layout;

const appMode = resolveAppMode(import.meta.env.VITE_AIRETEST_MODE);
const menuItems = getNavigationItems(appMode);

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const screens = Grid.useBreakpoint();
  const isMobile = screens.md === false;
  const { token: themeToken } = theme.useToken();
  const { user, logout, loading } = useAuth();
  const [openKeys, setOpenKeys] = useState<string[]>(() =>
    getOpenKeys(menuItems, location.pathname)
  );

  // 路径变化时，确保对应 SubMenu 展开（保留用户已展开的其他 SubMenu）
  // 注意：所有 hooks 必须在条件 return 之前调用，否则违反 React Hooks 规则
  useEffect(() => {
    const pathOpen = getOpenKeys(menuItems, location.pathname);
    setOpenKeys((prev) => {
      const merged = new Set(prev);
      pathOpen.forEach((k) => merged.add(k));
      return Array.from(merged);
    });
  }, [location.pathname]);

  useEffect(() => {
    if (!isMobile) {
      setMobileMenuOpen(false);
    }
  }, [isMobile]);

  // 认证守卫：加载中显示空白，加载完成且未登录才跳转
  if (loading) return null;
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const selectedItem = findNavigationItemByPath(
    allNavigationItems,
    location.pathname
  );
  const selectedKeys = selectedItem ? [selectedItem.key] : [];
  const handleMenuClick = (key: string) => {
    navigate(key);
    setMobileMenuOpen(false);
  };

  const menu = (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={selectedKeys}
      openKeys={openKeys}
      onOpenChange={(keys) => setOpenKeys(keys)}
      items={menuItems}
      onClick={({ key }) => handleMenuClick(key)}
      data-testid="sidebar-menu"
      style={{ borderInlineEnd: 0 }}
    />
  );

  const brand = (
    <div
      style={{
        height: 48,
        margin: 16,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontSize: collapsed && !isMobile ? 16 : 15,
        fontWeight: 700,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
      }}
    >
      {collapsed && !isMobile ? 'AI' : 'AI 测试平台'}
    </div>
  );

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
        {!isMobile && (
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
            {brand}
            {menu}
          </Sider>
        )}
        <Drawer
          placement="left"
          open={isMobile && mobileMenuOpen}
          onClose={() => setMobileMenuOpen(false)}
          closable={false}
          size={260}
          styles={{
            body: { padding: 0, background: '#0f172a' },
            header: { display: 'none' },
          }}
        >
          {brand}
          {menu}
        </Drawer>
        <Layout
          style={{
            marginLeft: isMobile ? 0 : collapsed ? 80 : 200,
            transition: 'all 0.2s',
          }}
        >
          <Header
            style={{
              padding: isMobile ? '0 12px' : '0 24px',
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
            <Space size="small" style={{ minWidth: 0, overflow: 'hidden' }}>
              {isMobile && (
                <Button
                  type="text"
                  icon={<MenuOutlined />}
                  aria-label="打开导航菜单"
                  onClick={() => setMobileMenuOpen(true)}
                />
              )}
              <span className="app-header-title" style={{ fontSize: 16, fontWeight: 600 }}>
                {selectedItem?.label ?? 'AI 测试平台'}
              </span>
            </Space>
            <Space
              className="app-header-actions"
              size={isMobile ? 'small' : 'large'}
              align="center"
            >
              {!isMobile && (
                <span style={{ color: '#6b7280', fontSize: 13 }}>
                  {dayjs().format('YYYY-MM-DD dddd')}
                </span>
              )}
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
                  <span className="app-user-name" style={{ fontSize: 14 }}>
                    {user.username}
                    {user.is_superuser && !isMobile && (
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
              margin: isMobile ? 8 : 24,
              padding: isMobile ? 12 : 24,
              background: '#f9fafb',
              borderRadius: isMobile ? 0 : 8,
              minHeight: 280,
              minWidth: 0,
            }}
          >
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}
