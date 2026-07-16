import { useEffect, useState, useMemo } from 'react';
import {
  Card,
  Select,
  Button,
  Space,
  Tag,
  Empty,
  Spin,
  message,
  Input,
  Collapse,
  Typography,
} from 'antd';
import {
  BookOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  FolderOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { testCaseApi, projectApi } from '../services/api';
import type { TestCase, Project } from '../types';

const { Text, Paragraph } = Typography;

// 方法对应的标签颜色
const methodColor: Record<string, string> = {
  GET: 'green',
  POST: 'orange',
  PUT: 'blue',
  PATCH: 'purple',
  DELETE: 'red',
};

// 格式化 JSON 为字符串展示
function formatJson(obj: any): string {
  if (!obj) return '';
  if (typeof obj === 'string') return obj;
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export default function ApiDocsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [cases, setCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  async function loadProjects() {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function loadCases() {
    setLoading(true);
    try {
      const params: any = { page: 1, page_size: 500 };
      if (selectedProjectId) params.project_id = selectedProjectId;
      const res = await testCaseApi.list(params);
      setCases(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    loadCases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  // 按分组组织接口
  const groupedCases = useMemo(() => {
    const filtered = cases.filter((c) => {
      if (!search) return true;
      const s = search.toLowerCase();
      return (
        c.title.toLowerCase().includes(s) ||
        c.url.toLowerCase().includes(s) ||
        (c.description || '').toLowerCase().includes(s) ||
        (c.group_path || '').toLowerCase().includes(s)
      );
    });

    const groups: Record<string, TestCase[]> = {};
    filtered.forEach((c) => {
      const g = c.group_path || '未分组';
      if (!groups[g]) groups[g] = [];
      groups[g].push(c);
    });

    // 按分组名排序，"未分组"放最后
    return Object.entries(groups).sort(([a], [b]) => {
      if (a === '未分组') return 1;
      if (b === '未分组') return -1;
      return a.localeCompare(b);
    });
  }, [cases, search]);

  // 跳转到接口调试页并预填数据
  function handleTryIt(c: TestCase) {
    const params = new URLSearchParams({
      method: c.method,
      url: c.url,
      headers: JSON.stringify(c.headers || {}),
      params: JSON.stringify(c.params || {}),
    });
    if (c.body) params.set('body', JSON.stringify(c.body));
    if (c.title) params.set('title', c.title);
    navigate(`/quick-test?${params.toString()}`);
  }

  // 渲染单个接口卡片
  function renderApiCard(c: TestCase) {
    const hasHeaders = c.headers && Object.keys(c.headers).length > 0;
    const hasParams = c.params && Object.keys(c.params).length > 0;
    const hasBody = c.body && Object.keys(c.body).length > 0;

    return (
      <Card
        key={c.id}
        size="small"
        style={{ marginBottom: 12 }}
        bodyStyle={{ padding: 16 }}
      >
        {/* 标题行：方法 + URL + 试一下按钮 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
          <Space wrap>
            <Tag color={methodColor[c.method] || 'default'} style={{ minWidth: 60, textAlign: 'center', fontWeight: 600 }}>
              {c.method}
            </Tag>
            <Text code copyable style={{ fontSize: 13 }}>
              {c.url}
            </Text>
          </Space>
          <Button
            type="primary"
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => handleTryIt(c)}
          >
            试一下
          </Button>
        </div>

        {/* 标题和描述 */}
        <div style={{ marginBottom: 8 }}>
          <Text strong style={{ fontSize: 15 }}>{c.title}</Text>
          {c.description && (
            <Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 0, fontSize: 13 }}>
              {c.description}
            </Paragraph>
          )}
        </div>

        {/* 标记 */}
        {c.markers && c.markers.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            {c.markers.map((m) => (
              <Tag key={m} color="blue" style={{ marginBottom: 2 }}>{m}</Tag>
            ))}
          </div>
        )}

        {/* 请求详情：可折叠 */}
        {(hasHeaders || hasParams || hasBody) && (
          <Collapse
            size="small"
            ghost
            items={[
              {
                key: 'detail',
                label: <span style={{ fontSize: 13, color: '#6b7280' }}>请求详情</span>,
                children: (
                  <div>
                    {hasHeaders && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Headers</div>
                        <pre style={{ background: '#f9fafb', padding: 8, borderRadius: 6, fontSize: 12, overflow: 'auto', margin: 0 }}>
                          {formatJson(c.headers)}
                        </pre>
                      </div>
                    )}
                    {hasParams && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Query Params</div>
                        <pre style={{ background: '#f9fafb', padding: 8, borderRadius: 6, fontSize: 12, overflow: 'auto', margin: 0 }}>
                          {formatJson(c.params)}
                        </pre>
                      </div>
                    )}
                    {hasBody && (
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Body 示例</div>
                        <pre style={{ background: '#f9fafb', padding: 8, borderRadius: 6, fontSize: 12, overflow: 'auto', margin: 0 }}>
                          {formatJson(c.body)}
                        </pre>
                      </div>
                    )}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Card>
    );
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <BookOutlined />
            <span>接口文档</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {cases.length} 个接口
            </span>
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              style={{ width: 240 }}
              placeholder="选择项目"
              showSearch
              optionFilterProp="label"
              allowClear
              options={[
                { value: '', label: '全部项目' },
                ...projects.map((p) => ({ value: p.id, label: p.name })),
              ]}
            />
            <Input.Search
              placeholder="搜索接口名称、URL、描述"
              allowClear
              style={{ width: 260 }}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              prefix={<SearchOutlined />}
            />
            <Button icon={<ReloadOutlined />} onClick={loadCases} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin tip="加载接口文档..." />
          </div>
        ) : groupedCases.length === 0 ? (
          <Empty description="暂无接口，请先在接口定义中创建或导入" style={{ padding: 40 }} />
        ) : (
          <div>
            {groupedCases.map(([groupName, groupCases]) => (
              <div key={groupName} style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, paddingBottom: 8, borderBottom: '2px solid #4f46e5' }}>
                  <FolderOutlined style={{ color: '#4f46e5' }} />
                  <span style={{ fontSize: 16, fontWeight: 600 }}>{groupName}</span>
                  <Tag>{groupCases.length} 个接口</Tag>
                </div>
                {groupCases.map((c) => renderApiCard(c))}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
