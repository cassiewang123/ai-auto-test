import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table, Tag, Empty, Spin } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { environmentApi, testCaseApi, testPlanApi } from '../services/api';
import type { TestCase } from '../types';

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [envCount, setEnvCount] = useState(0);
  const [caseCount, setCaseCount] = useState(0);
  const [planCount, setPlanCount] = useState(0);
  const [recentCases, setRecentCases] = useState<TestCase[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const [envs, cases, plans] = await Promise.all([
          environmentApi.list({ page: 1, page_size: 1 }),
          testCaseApi.list({ page: 1, page_size: 5 }),
          testPlanApi.list({ page: 1, page_size: 1 }),
        ]);
        setEnvCount(envs.total);
        setCaseCount(cases.total);
        setPlanCount(plans.total);
        setRecentCases(cases.data || []);
      } catch {
        // 后端未启动时静默
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const methodColor: Record<string, string> = {
    GET: 'green',
    POST: 'orange',
    PUT: 'blue',
    PATCH: 'purple',
    DELETE: 'red',
  };

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }} data-testid="stats-cards">
        <Col span={6}>
          <Card>
            <Statistic
              title="环境数量"
              value={envCount}
              prefix={<FileTextOutlined />}
              styles={{ content: { color: '#4f46e5' } }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="测试用例"
              value={caseCount}
              prefix={<CheckCircleOutlined />}
              styles={{ content: { color: '#0891b2' } }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="测试计划"
              value={planCount}
              prefix={<ClockCircleOutlined />}
              styles={{ content: { color: '#059669' } }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平台状态"
              value="运行中"
              prefix={<CheckCircleOutlined />}
              styles={{ content: { color: '#0d9488' } }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="最近用例" data-testid="recent-cases">
        {recentCases.length === 0 ? (
          <Empty description="暂无用例，请前往用例管理创建" />
        ) : (
          <Table
            dataSource={recentCases}
            rowKey="id"
            pagination={false}
            columns={[
              {
                title: '方法',
                dataIndex: 'method',
                width: 80,
                render: (m: string) => (
                  <Tag color={methodColor[m] || 'default'}>{m}</Tag>
                ),
              },
              { title: '标题', dataIndex: 'title' },
              { title: 'URL', dataIndex: 'url', ellipsis: true },
              {
                title: '标记',
                dataIndex: 'markers',
                render: (markers: string[]) =>
                  (markers || []).map((m) => (
                    <Tag key={m} color="blue">
                      {m}
                    </Tag>
                  )),
              },
              {
                title: '创建时间',
                dataIndex: 'created_at',
                render: (t: string) => new Date(t).toLocaleString('zh-CN'),
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
