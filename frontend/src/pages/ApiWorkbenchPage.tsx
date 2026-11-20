/** API 测试工作台：汇总资产、用例与最近执行，提供常用入口。 */
import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Button, Space, Tag, Typography, List, Empty } from 'antd';
import {
  ApiOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
  DatabaseOutlined,
  HistoryOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { testCaseApi, historyApi, projectApi } from '../services/api';
import type { CallHistoryRecord } from '../services/api';
import type { TestCase, Project } from '../types';

export default function ApiWorkbenchPage() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<TestCase[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [history, setHistory] = useState<CallHistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      testCaseApi.list({ page: 1, page_size: 500 }),
      projectApi.list({ page: 1, page_size: 500 }),
      historyApi.list({ page: 1, page_size: 8 }),
    ])
      .then(([caseRes, projectRes, historyRes]) => {
        setCases(caseRes.data || []);
        setProjects(projectRes.data || []);
        setHistory(Array.isArray(historyRes.data) ? historyRes.data : []);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  const entries = [
    { title: '接口定义', icon: <ApiOutlined />, path: '/api-list', color: '#2563eb', desc: '管理所有接口请求定义' },
    { title: '接口资产', icon: <DatabaseOutlined />, path: '/api-assets', color: '#0891b2', desc: '按服务浏览与导入资产' },
    { title: '用例管理', icon: <UnorderedListOutlined />, path: '/test-cases', color: '#7c3aed', desc: '执行与断言测试用例' },
    { title: '接口调试', icon: <ThunderboltOutlined />, path: '/quick-test', color: '#16a34a', desc: '快速发起单次请求' },
    { title: '接口导入', icon: <ApiOutlined />, path: '/import', color: '#ea580c', desc: 'OpenAPI / Postman / 文档' },
    { title: '历史记录', icon: <HistoryOutlined />, path: '/history', color: '#dc2626', desc: '查看调用与执行历史' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={12}>
        {[
          { title: '接口数', value: cases.length, color: '#2563eb' },
          { title: '项目数', value: projects.length, color: '#0891b2' },
          { title: '服务数', value: new Set(cases.map((c) => (c.group_path || '').split('/')[0]).filter(Boolean)).size, color: '#7c3aed' },
        ].map((item) => (
          <Col span={8} key={item.title}>
            <Card size="small" loading={loading}>
              <Statistic title={item.title} value={item.value} valueStyle={{ color: item.color, fontSize: 26, fontWeight: 600 }} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card size="small" title="快捷入口">
        <Row gutter={[12, 12]}>
          {entries.map((entry) => (
            <Col xs={24} sm={12} md={8} key={entry.title}>
              <Card size="small" hoverable onClick={() => navigate(entry.path)}>
                <Space align="start" size={12}>
                  <span style={{ color: entry.color, fontSize: 22 }}>{entry.icon}</span>
                  <div>
                    <Typography.Text strong>{entry.title}</Typography.Text>
                    <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 2 }}>{entry.desc}</div>
                  </div>
                  <ArrowRightOutlined style={{ marginLeft: 'auto', color: '#cbd5e1' }} />
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card size="small" title="最近执行" extra={<Button type="link" onClick={() => navigate('/history')}>全部记录</Button>}>
        {history.length === 0 ? (
          <Empty description="暂无执行记录" />
        ) : (
          <List
            size="small"
            dataSource={history}
            renderItem={(item) => (
              <List.Item>
                <Space>
                  <Tag color={item.method === 'POST' ? 'green' : 'blue'}>{item.method}</Tag>
                  <Typography.Text ellipsis style={{ maxWidth: 520 }}>{item.url}</Typography.Text>
                </Space>
                <Tag color={item.status === 'passed' ? 'green' : 'red'}>{item.status}</Tag>
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>
  );
}
