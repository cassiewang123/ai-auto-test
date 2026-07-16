import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  message,
  Popconfirm,
  Tag,
  Card,
  List,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { testPlanApi, testCaseApi, projectApi } from '../services/api';
import type { TestPlan, TestPlanCreate, TestCase, Project } from '../types';

const EXEC_MODES = [
  { label: '顺序执行', value: 'sequential' },
  { label: '并行执行', value: 'parallel' },
  { label: '压力测试', value: 'stress' },
];

export default function TestPlansPage() {
  const [data, setData] = useState<TestPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TestPlan | null>(null);
  const [form] = Form.useForm();

  // 详情抽屉
  const [detailPlan, setDetailPlan] = useState<TestPlan | null>(null);
  const [allCases, setAllCases] = useState<TestCase[]>([]);
  const [addCaseModal, setAddCaseModal] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string>('');

  async function loadData(
    p = page,
    ps = pageSize,
    projectId = selectedProjectId,
  ) {
    setLoading(true);
    try {
      const res = await testPlanApi.list({
        page: p,
        page_size: ps,
        project_id: projectId || undefined,
      });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    projectApi
      .listAll()
      .then((res) => setProjects(res.data || []))
      .catch((e: any) => message.error(e.message));
    loadData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      execution_mode: 'sequential',
      project_id: selectedProjectId || undefined,
    });
    setModalOpen(true);
  }

  function openEdit(record: TestPlan) {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      const payload: Omit<TestPlanCreate, 'project_id'> = {
        name: values.name,
        description: values.description,
        execution_mode: values.execution_mode,
        marker_filter: values.marker_filter,
      };
      if (editing) {
        await testPlanApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await testPlanApi.create({
          ...payload,
          project_id: values.project_id,
        });
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    }
  }

  async function handleDelete(id: string) {
    try {
      await testPlanApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function openDetail(record: TestPlan) {
    try {
      const res = await testPlanApi.get(record.id);
      setDetailPlan(res.data);
      const casesRes = await testCaseApi.list({
        page: 1,
        page_size: 100,
        project_id: res.data.project_id,
      });
      setAllCases(casesRes.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleAddCase() {
    if (!detailPlan || !selectedCaseId) return;
    try {
      const order =
        (detailPlan.items?.length || 0) +
        1;
      await testPlanApi.addItem(detailPlan.id, {
        test_case_id: selectedCaseId,
        order,
      });
      message.success('添加成功');
      const res = await testPlanApi.get(detailPlan.id);
      setDetailPlan(res.data);
      setAddCaseModal(false);
      setSelectedCaseId('');
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleRemoveCase(caseId: string) {
    if (!detailPlan) return;
    try {
      await testPlanApi.removeItem(detailPlan.id, caseId);
      message.success('移除成功');
      const res = await testPlanApi.get(detailPlan.id);
      setDetailPlan(res.data);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const modeColor: Record<string, string> = {
    sequential: 'blue',
    parallel: 'cyan',
    stress: 'red',
  };
  const projectNameMap = new Map(projects.map((project) => [project.id, project.name]));

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Select
            allowClear
            placeholder="全部项目"
            style={{ width: 220 }}
            value={selectedProjectId || undefined}
            options={projects.map((project) => ({
              label: project.name,
              value: project.id,
            }))}
            onChange={(value) => {
              const projectId = value || '';
              setSelectedProjectId(projectId);
              setPage(1);
              loadData(1, pageSize, projectId);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
            刷新
          </Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建计划
        </Button>
      </div>

      <Table
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
            loadData(p, ps);
          },
        }}
        columns={[
          { title: '计划名称', dataIndex: 'name' },
          {
            title: '所属项目',
            dataIndex: 'project_id',
            width: 160,
            render: (projectId?: string) =>
              projectId ? projectNameMap.get(projectId) || projectId : '-',
          },
          {
            title: '执行模式',
            dataIndex: 'execution_mode',
            width: 100,
            render: (m: string) => (
              <Tag color={modeColor[m] || 'default'}>{m}</Tag>
            ),
          },
          {
            title: '用例数',
            width: 80,
            render: (_, r) => r.items?.length || 0,
          },
          { title: '标记筛选', dataIndex: 'marker_filter', width: 100 },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 180,
            render: (t: string) => new Date(t).toLocaleString('zh-CN'),
          },
          {
            title: '操作',
            width: 250,
            render: (_, record) => (
              <Space>
                <Button size="small" onClick={() => openDetail(record)}>
                  详情
                </Button>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openEdit(record)}
                >
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除？"
                  onConfirm={() => handleDelete(record.id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      {/* 创建/编辑 Modal */}
      <Modal
        title={editing ? '编辑计划' : '新建计划'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="project_id"
            label="所属项目"
            rules={[{ required: true, message: '请选择所属项目' }]}
          >
            <Select
              disabled={!!editing}
              placeholder="选择项目"
              options={projects.map((project) => ({
                label: project.name,
                value: project.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label="计划名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：用户模块冒烟测试" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="计划描述（可选）" />
          </Form.Item>
          <Form.Item name="execution_mode" label="执行模式">
            <Select options={EXEC_MODES} />
          </Form.Item>
          <Form.Item name="marker_filter" label="标记筛选">
            <Input placeholder="如：smoke（仅执行匹配标记的用例）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情 Modal */}
      <Modal
        title={detailPlan ? `计划详情：${detailPlan.name}` : ''}
        open={!!detailPlan}
        onCancel={() => setDetailPlan(null)}
        footer={null}
        width={700}
      >
        {detailPlan && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Tag color={modeColor[detailPlan.execution_mode]}>
                  {detailPlan.execution_mode}
                </Tag>
                {detailPlan.marker_filter && (
                  <Tag color="blue">筛选: {detailPlan.marker_filter}</Tag>
                )}
                <span style={{ color: '#6b7280' }}>
                  共 {detailPlan.items?.length || 0} 条用例
                </span>
              </Space>
            </div>
            <Card
              size="small"
              title="用例列表"
              extra={
                <Button
                  size="small"
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setAddCaseModal(true)}
                >
                  添加用例
                </Button>
              }
            >
              <List
                size="small"
                dataSource={detailPlan.items || []}
                locale={{ emptyText: '暂无用例' }}
                renderItem={(item, idx) => (
                  <List.Item
                    actions={[
                      <Popconfirm
                        key="remove"
                        title="确认移除？"
                        onConfirm={() => handleRemoveCase(item.test_case_id)}
                      >
                        <Button size="small" danger icon={<DeleteOutlined />}>
                          移除
                        </Button>
                      </Popconfirm>,
                    ]}
                  >
                    <Space>
                      <Tag>{idx + 1}</Tag>
                      <span style={{ fontWeight: 500 }}>
                        {item.test_case?.title || item.test_case_id}
                      </span>
                      {item.test_case && (
                        <Tag color="blue">{item.test_case.method}</Tag>
                      )}
                    </Space>
                  </List.Item>
                )}
              />
            </Card>
          </div>
        )}
      </Modal>

      {/* 添加用例 Modal */}
      <Modal
        title="选择用例添加到计划"
        open={addCaseModal}
        onOk={handleAddCase}
        onCancel={() => setAddCaseModal(false)}
      >
        <Select
          placeholder="选择测试用例"
          style={{ width: '100%' }}
          showSearch
          optionFilterProp="label"
          value={selectedCaseId || undefined}
          onChange={setSelectedCaseId}
          options={allCases.map((c) => ({
            label: `[${c.method}] ${c.title}`,
            value: c.id,
          }))}
        />
      </Modal>
    </div>
  );
}
