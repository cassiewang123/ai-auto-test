import { useState, useEffect } from 'react';
import { Layout, Menu, theme, ConfigProvider, Space, Avatar, Dropdown } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
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
  const location = useLocation();
  const navigate = useNavigate();
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
            selectedKeys={selectedKeys}
            openKeys={openKeys}
            onOpenChange={(keys) => setOpenKeys(keys)}
            items={menuItems}
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
              {selectedItem?.label ?? 'AI 测试平台'}
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
