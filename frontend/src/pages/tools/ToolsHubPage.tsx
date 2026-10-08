import { Card } from 'antd';
import {
  ArrowRightOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import ToolPage from '../../components/ToolPage';
import { toolDefinitions, toolIcons } from './toolCatalog';

export default function ToolsHubPage() {
  const navigate = useNavigate();

  return (
    <ToolPage
      icon={<ToolOutlined />}
      title="工具集"
      description="测试工作常用工具，全部在浏览器本地处理，数据不会上传。"
    >
      <div className="tools-hub-grid">
        {toolDefinitions.map((tool) => (
          <Card
            key={tool.id}
            className="tools-hub-card"
            hoverable
            onClick={() => navigate(tool.path)}
            data-testid={`tool-card-${tool.id}`}
          >
            <div className="tools-hub-card-top">
              <span className="tools-hub-icon">{toolIcons[tool.icon]}</span>
            </div>
            <h2 className="tools-hub-name">{tool.name}</h2>
            <div className="tools-hub-description">{tool.description}</div>
            <div className="tools-hub-footer">
              打开工具 <ArrowRightOutlined />
            </div>
          </Card>
        ))}
      </div>
    </ToolPage>
  );
}
