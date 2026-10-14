/** 右侧内容区的多标签页导航条。 */
import { Dropdown, Tabs, theme } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { DEFAULT_HOME, usePageTabs } from '../contexts/PageTabsContext';

export default function PageTabs() {
  const { token } = theme.useToken();
  const {
    tabs,
    activeKey,
    selectTab,
    closeTab,
    closeOtherTabs,
    closeAllTabs,
    refreshTab,
  } = usePageTabs();

  if (tabs.length === 0) return null;

  return (
    <div
      className="page-tabs-bar"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 8px 0',
        background: token.colorBgContainer,
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
      }}
      data-testid="page-tabs"
    >
      <Tabs
        type="editable-card"
        size="small"
        activeKey={activeKey}
        onChange={selectTab}
        onEdit={(targetKey, action) => {
          if (action === 'remove') closeTab(String(targetKey));
        }}
        hideAdd
        tabBarStyle={{ marginBottom: 0 }}
        style={{ flex: 1, minWidth: 0 }}
        items={tabs.map((tab) => ({
          key: tab.path,
          label: (
            <Dropdown
              trigger={['contextMenu']}
              menu={{
                items: [
                  {
                    key: 'refresh',
                    icon: <ReloadOutlined />,
                    label: '刷新本页',
                    onClick: () => refreshTab(tab.path),
                  },
                  {
                    key: 'closeOthers',
                    label: '关闭其他标签',
                    disabled: tabs.length <= 1,
                    onClick: () => closeOtherTabs(tab.path),
                  },
                  {
                    key: 'closeAll',
                    label: '关闭全部标签',
                    onClick: closeAllTabs,
                  },
                ],
              }}
            >
              <span style={{ display: 'inline-block' }} title={tab.path}>
                {tab.label}
              </span>
            </Dropdown>
          ),
          // 首页固定保留，避免用户关掉所有标签后没有落点
          closable: tab.path !== DEFAULT_HOME.path,
        }))}
      />
      <Dropdown
        trigger={['click']}
        menu={{
          items: [
            {
              key: 'reload',
              icon: <ReloadOutlined />,
              label: '刷新当前页',
              onClick: () => refreshTab(activeKey),
            },
            {
              key: 'closeOthers',
              label: '关闭其他标签',
              disabled: tabs.length <= 1,
              onClick: () => closeOtherTabs(activeKey),
            },
            {
              key: 'closeAll',
              label: '关闭全部标签',
              onClick: closeAllTabs,
            },
          ],
        }}
      >
        <span
          role="button"
          aria-label="标签页操作"
          style={{
            cursor: 'pointer',
            color: token.colorTextSecondary,
            padding: '0 6px 6px',
            lineHeight: '24px',
          }}
        >
          ⋯
        </span>
      </Dropdown>
    </div>
  );
}
