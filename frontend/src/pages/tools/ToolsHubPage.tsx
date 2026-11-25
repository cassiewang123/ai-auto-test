import { useMemo, useState } from 'react';
import { Button, Card, Empty, Input, Segmented, Space, Tag } from 'antd';
import {
  ArrowRightOutlined,
  ClockCircleOutlined,
  SearchOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import ToolPage from '../../components/ToolPage';
import {
  toolCategoryOptions,
  toolDefinitions,
  toolIcons,
  type ToolCategory,
  type ToolDefinition,
} from './toolCatalog';
import { useRecentTools } from './useRecentTools';

/** 「全部」+ 4 个分类的筛选值。 */
type CategoryFilter = ToolCategory | 'all';

const ALL_CATEGORY: CategoryFilter = 'all';

export default function ToolsHubPage() {
  const navigate = useNavigate();
  const [keyword, setKeyword] = useState('');
  const [category, setCategory] = useState<CategoryFilter>(ALL_CATEGORY);
  const { recent, record, clear } = useRecentTools();

  // 各分类工具数量：全部 / JSON / 文本 / 开发 / 服务器
  const categoryCounts = useMemo(() => {
    const counts: Record<CategoryFilter, number> = {
      all: toolDefinitions.length,
      json: 0,
      text: 0,
      dev: 0,
      network: 0,
    };
    for (const tool of toolDefinitions) {
      counts[tool.category] += 1;
    }
    return counts;
  }, []);

  const categorySegments = useMemo(
    () => [
      { value: ALL_CATEGORY, label: `全部 ${categoryCounts.all}` },
      ...toolCategoryOptions.map((option) => ({
        value: option.value,
        label: `${option.label} ${categoryCounts[option.value]}`,
      })),
    ],
    [categoryCounts]
  );

  // 搜索（名称 / 描述 / id）+ 分类 双重过滤，受控即时生效
  const visibleTools = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    return toolDefinitions.filter((tool) => {
      if (category !== ALL_CATEGORY && tool.category !== category) return false;
      if (!query) return true;
      return [tool.name, tool.description, tool.id].some((field) =>
        field.toLowerCase().includes(query)
      );
    });
  }, [category, keyword]);

  // 最近使用：过滤掉目录中已不存在的工具
  const recentTools = useMemo(
    () =>
      recent.flatMap((entry) => {
        const tool = toolDefinitions.find((item) => item.id === entry.id);
        return tool ? [{ id: entry.id, tool }] : [];
      }),
    [recent]
  );

  function openTool(tool: ToolDefinition) {
    record(tool.id);
    navigate(tool.path);
  }

  return (
    <ToolPage
      icon={<ToolOutlined />}
      title="工具集"
      description="测试工作常用工具；服务器连接会通过后端 SSH 连接到目标服务器。部分能力默认关闭。"
    >
      <div className="tools-hub-toolbar">
        <Input
          allowClear
          className="tools-hub-search"
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索工具名称、描述或标识"
          data-testid="tools-search"
        />
        <Segmented
          value={category}
          options={categorySegments}
          onChange={(value) => setCategory(value as CategoryFilter)}
          data-testid="tools-category"
        />
      </div>

      {recentTools.length > 0 ? (
        <div className="tools-hub-recent" data-testid="tools-recent">
          <Space size={8} wrap>
            <span className="tools-hub-recent-title">
              <ClockCircleOutlined /> 最近使用
            </span>
            {recentTools.map((item) => (
              <Button
                key={item.id}
                size="small"
                onClick={() => openTool(item.tool)}
                data-testid={`tool-recent-${item.id}`}
              >
                {item.tool.name}
              </Button>
            ))}
            <Button
              size="small"
              type="link"
              onClick={clear}
              data-testid="tools-recent-clear"
            >
              清空
            </Button>
          </Space>
        </div>
      ) : null}

      {visibleTools.length === 0 ? (
        <Card size="small" data-testid="tools-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="没有匹配的工具，试试调整搜索词或切换分类"
          />
        </Card>
      ) : (
        <div className="tools-hub-grid">
          {visibleTools.map((tool) => (
            <Card
              key={tool.id}
              className="tools-hub-card"
              hoverable
              onClick={() => openTool(tool)}
              data-testid={`tool-card-${tool.id}`}
            >
              <div className="tools-hub-card-top">
                <span className="tools-hub-icon">{toolIcons[tool.icon]}</span>
                <Tag color={tool.safety === 'high-risk' ? 'red' : 'green'}>
                  {tool.safety === 'high-risk' ? '高风险 · 默认关闭' : '本机处理 · 不外发'}
                </Tag>
              </div>
              <h2 className="tools-hub-name">{tool.name}</h2>
              <div className="tools-hub-description">{tool.description}</div>
              <div className="tools-hub-footer">
                打开工具 <ArrowRightOutlined />
              </div>
            </Card>
          ))}
        </div>
      )}
    </ToolPage>
  );
}
