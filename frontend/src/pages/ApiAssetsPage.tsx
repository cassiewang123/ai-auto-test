/** 接口资产库：按服务分组浏览已沉淀的接口定义，并快速导入为可执行用例。 */
import { useEffect, useMemo, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Input,
  message,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  ImportOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { testCaseApi, projectApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';
import type { Project, TestCase } from '../types';

const methodColors: Record<string, string> = {
  GET: 'blue',
  POST: 'green',
  PUT: 'orange',
  PATCH: 'purple',
  DELETE: 'red',
};

type GroupMode = 'service' | 'project' | 'method';

function serviceOf(caseItem: TestCase): string {
  const segments = (caseItem.group_path || '').split('/').filter(Boolean);
  if (segments.length > 1) return segments[0];
  return segments[0] || '未分组';
}

function shortUrl(url: string): string {
  return url.replace(/\{\{[^}]+\}\}/g, '{变量}');
}

export default function ApiAssetsPage() {
  const navigate = useNavigate();
  const { selectedProjectId } = useWorkspace();
  const [cases, setCases] = useState<TestCase[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [service, setService] = useState<string>('');
  const [method, setMethod] = useState<string>('');
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [groupMode, setGroupMode] = useState<GroupMode>('service');
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const [caseRes, projectRes] = await Promise.all([
        testCaseApi.list({ page: 1, page_size: 500 }),
        projectApi.list(),
      ]);
      setCases(caseRes.data || []);
      setProjects(projectRes.data || []);
    } catch (e: any) {
      message.error(e.message || '加载接口资产失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const serviceOptions = useMemo(
    () => Array.from(new Set(cases.map(serviceOf))).sort((a, b) => a.localeCompare(b)),
    [cases]
  );
  const methodOptions = useMemo(
    () => Array.from(new Set(cases.map((item) => item.method))).sort(),
    [cases]
  );

  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    return cases.filter((item) => {
      if (projectFilter && (item.project_id || '') !== projectFilter) return false;
      if (service && serviceOf(item) !== service) return false;
      if (method && item.method !== method) return false;
      if (!key) return true;
      return (
        item.title.toLowerCase().includes(key) ||
        item.url.toLowerCase().includes(key) ||
        (item.group_path || '').toLowerCase().includes(key)
      );
    });
  }, [cases, keyword, service, method, projectFilter]);

  const grouped = useMemo(() => {
    const map = new Map<string, TestCase[]>();
    for (const item of filtered) {
      const key =
        groupMode === 'service'
          ? serviceOf(item)
          : groupMode === 'project'
            ? projects.find((p) => p.id === item.project_id)?.name || '未归属项目'
            : item.method;
      const list = map.get(key) || [];
      list.push(item);
      map.set(key, list);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered, groupMode, projects]);

  const stats = useMemo(
    () => ({
      total: cases.length,
      projects: new Set(cases.map((item) => item.project_id).filter(Boolean)).size,
      services: serviceOptions.length,
      selected: selectedKeys.length,
    }),
    [cases, projectFilter, serviceOptions.length, selectedKeys.length]
  );

  async function importSelected() {
    if (!selectedKeys.length) {
      message.warning('请先勾选要导入的接口');
      return;
    }
    setImporting(true);
    try {
      const existingIds = new Set(cases.map((item) => item.id));
      const toCreate = selectedKeys.filter((id) => !existingIds.has(id));
      let created = 0;
      for (const id of toCreate) {
        const item = cases.find((entry) => entry.id === id);
        if (!item) continue;
        await testCaseApi.create({
          title: item.title,
          method: item.method,
          url: item.url,
          headers: item.headers,
          params: item.params,
          body: item.body,
          group_path: item.group_path,
          project_id: item.project_id || selectedProjectId || undefined,
          files: item.files,
          extract_rules: item.extract_rules,
          assertions: item.assertions,
        });
        created += 1;
      }
      message.success(`已导入 ${created} 个接口到单接口用例`);
      setSelectedKeys([]);
      await loadData();
    } catch (e: any) {
      message.error(e.message || '导入失败');
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small">
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Space wrap size={12}>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="搜索接口名称、URL、分组"
                style={{ width: 280 }}
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
              <Select
                allowClear
                placeholder="全部项目"
                style={{ width: 180 }}
                value={projectFilter || undefined}
                onChange={(value) => setProjectFilter(value || '')}
                options={projects.map((item) => ({ label: item.name, value: item.id }))}
              />
              <Select
                allowClear
                placeholder="全部服务"
                style={{ width: 200 }}
                value={service || undefined}
                onChange={(value) => setService(value || '')}
                options={serviceOptions.map((item) => ({ label: item, value: item }))}
              />
              <Select
                allowClear
                placeholder="全部方法"
                style={{ width: 120 }}
                value={method || undefined}
                onChange={(value) => setMethod(value || '')}
                options={methodOptions.map((item) => ({ label: item, value: item }))}
              />
              <Button icon={<ReloadOutlined />} onClick={() => void loadData()} loading={loading}>
                刷新
              </Button>
            </Space>
          </Col>
          <Col>
            <Space>
              <Button
                icon={<ImportOutlined />}
                loading={importing}
                disabled={!selectedKeys.length}
                onClick={() => void importSelected()}
              >
                导入为用例
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/import')}>
                导入新资产
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={12}>
        {[
          { title: '接口总数', value: stats.total, color: '#2563eb' },
          { title: '项目数', value: stats.projects, color: '#0891b2' },
          { title: '服务/分组', value: stats.services, color: '#7c3aed' },
          { title: '已选接口', value: stats.selected, color: '#16a34a' },
        ].map((item) => (
          <Col span={6} key={item.title}>
            <Card size="small">
              <Statistic
                title={item.title}
                value={item.value}
                valueStyle={{ color: item.color, fontSize: 24, fontWeight: 600 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        size="small"
        title={
          <Space>
            <ApiOutlined />
            <span>接口资产</span>
            <Badge count={filtered.length} showZero color="#94a3b8" />
          </Space>
        }
        extra={
          <Segmented<GroupMode>
            value={groupMode}
            onChange={setGroupMode}
            options={[
              { label: '按服务', value: 'service' },
              { label: '按项目', value: 'project' },
              { label: '按方法', value: 'method' },
            ]}
          />
        }
      >
        {filtered.length === 0 ? (
          <Empty description="暂无接口资产，请先导入 OpenAPI / Postman / Word / Excel" />
        ) : (
          <Table<TestCase>
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={filtered}
            pagination={{ pageSize: 12, showSizeChanger: true }}
            rowSelection={{
              selectedRowKeys: selectedKeys,
              onChange: (keys) => setSelectedKeys(keys as string[]),
            }}
            columns={[
              {
                title: '接口名称',
                dataIndex: 'title',
                ellipsis: true,
                render: (value: string, record) => (
                  <Tooltip title={`${value}\n${record.url}`}>
                    <Space size={6}>
                      <Typography.Text strong>{value}</Typography.Text>
                      {(record.files || []).length > 0 && <Tag color="cyan">文件</Tag>}
                    </Space>
                  </Tooltip>
                ),
              },
              {
                title: '方法',
                dataIndex: 'method',
                width: 80,
                render: (value: string) => (
                  <Tag color={methodColors[value] || 'default'}>{value}</Tag>
                ),
              },
              {
                title: '分组 / 服务',
                dataIndex: 'group_path',
                ellipsis: true,
                render: (value: string) => value || '-',
              },
              {
                title: 'URL',
                dataIndex: 'url',
                ellipsis: true,
                render: (value: string) => (
                  <Typography.Text code copyable={{ text: value }}>
                    {shortUrl(value)}
                  </Typography.Text>
                ),
              },
              {
                title: '状态',
                key: 'status',
                width: 90,
                render: () => (
                  <Tag icon={<CheckCircleOutlined />} color="green">
                    已沉淀
                  </Tag>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card size="small" title="服务概览">
        <Row gutter={[12, 12]}>
          {grouped.map(([name, items]) => (
            <Col xs={24} sm={12} md={8} lg={6} key={name}>
              <Button
                block
                style={{ height: 44, textAlign: 'left' }}
                onClick={() => {
                  setService(groupMode === 'service' ? name : '');
                  setKeyword('');
                }}
              >
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <span>{name}</span>
                  <Badge count={items.length} showZero color="#e2e8f0" style={{ color: '#475569' }} />
                </Space>
              </Button>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
