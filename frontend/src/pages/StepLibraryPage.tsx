import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Input,
  Select,
  Modal,
  Form,
  message,
  Popconfirm,
  Empty,
  Tooltip,
  InputNumber,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CopyOutlined,
  EyeOutlined,
  ApartmentOutlined,
  ImportOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { stepLibraryApi, projectApi, uiTestCaseApi } from '../services/api';
import type { Project } from '../types';

// 主题色
const PRIMARY_COLOR = '#4f46e5';

// 步骤动作中文名映射（用于详情展示）
const ACTION_LABELS: Record<string, string> = {
  navigate: '导航',
  click: '点击',
  input: '输入',
  assert: '断言',
  wait: '等待',
  screenshot: '截图',
  select: '选择',
  press: '按键',
  hover: '悬停',
  drag: '拖拽',
  scroll: '滚动',
  upload: '上传',
  download: '下载',
  step_group: '步骤组引用',
};

export default function StepLibraryPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [projects, setProjects] = useState<Project[]>([]);
  const [filterProject, setFilterProject] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState('');

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 详情预览
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 从用例导入
  const [importOpen, setImportOpen] = useState(false);
  const [importCases, setImportCases] = useState<any[]>([]);
  const [importLoading, setImportLoading] = useState(false);
  const [importForm] = Form.useForm();

  async function loadData(
    p = page,
    ps = pageSize,
    projectId = filterProject,
    kw = search
  ) {
    setLoading(true);
    try {
      const res = await stepLibraryApi.list({
        page: p,
        page_size: ps,
        project_id: projectId,
        search: kw || undefined,
      });
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadProjects() {
    try {
      const res = await projectApi.listAll();
      setProjects(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  useEffect(() => {
    loadData(1);
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 打开详情并展开步骤
  async function openDetail(record: any) {
    setDetailOpen(true);
    setDetail(null);
    setDetailLoading(true);
    try {
      const res = await stepLibraryApi.expand(record.id);
      setDetail(res.data);
    } catch (e: any) {
      message.error(e.message);
      // 兜底用列表数据
      setDetail(record);
    } finally {
      setDetailLoading(false);
    }
  }

  // 打开新建
  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      name: '',
      description: '',
      project_id: filterProject,
      tags: [],
      stepsText: '[]',
    });
    setModalOpen(true);
  }

  // 打开编辑
  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description || '',
      project_id: record.project_id,
      tags: record.tags || [],
      stepsText: JSON.stringify(record.steps || [], null, 2),
    });
    setModalOpen(true);
  }

  // 保存（新建/编辑）
  async function handleSave() {
    try {
      const values = await form.validateFields();
      // 解析步骤 JSON
      let steps: any[] = [];
      try {
        steps = JSON.parse(values.stepsText || '[]');
        if (!Array.isArray(steps)) {
          throw new Error('步骤必须是数组');
        }
      } catch (e: any) {
        message.error('步骤 JSON 格式错误: ' + e.message);
        return;
      }
      const payload = {
        name: values.name,
        description: values.description || null,
        project_id: values.project_id || null,
        tags: values.tags || [],
        steps,
      };
      setSaving(true);
      if (editing) {
        await stepLibraryApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await stepLibraryApi.create(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e?.errorFields) return; // 表单校验错误
      message.error(e.message || '保存失败');
    } finally {
      setSaving(false);
    }
  }

  // 复制
  async function handleDuplicate(record: any) {
    try {
      await stepLibraryApi.duplicate(record.id);
      message.success('复制成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 删除
  async function handleDelete(record: any) {
    try {
      await stepLibraryApi.delete(record.id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 打开从用例导入
  async function openImport() {
    importForm.resetFields();
    importForm.setFieldsValue({
      name: '',
      description: '',
      start_index: 0,
      end_index: null,
    });
    setImportOpen(true);
    setImportLoading(true);
    try {
      const pageSize = 100;
      const firstPage = await uiTestCaseApi.list({
        page: 1,
        page_size: pageSize,
      });
      const cases = [...(firstPage.data || [])];
      const total = firstPage.total || cases.length;

      for (let currentPage = 2; cases.length < total; currentPage += 1) {
        const nextPage = await uiTestCaseApi.list({
          page: currentPage,
          page_size: pageSize,
        });
        const items = nextPage.data || [];
        if (items.length === 0) break;
        cases.push(...items);
      }

      setImportCases(cases);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setImportLoading(false);
    }
  }

  // 执行从用例提取步骤
  async function handleImport() {
    try {
      const values = await importForm.validateFields();
      if (!values.case_id) {
        message.error('请选择 UI 用例');
        return;
      }
      setImportLoading(true);
      await uiTestCaseApi.extractSteps(values.case_id, {
        name: values.name,
        description: values.description || undefined,
        start_index: values.start_index ?? 0,
        end_index: values.end_index ?? undefined,
        project_id: values.project_id || undefined,
      });
      message.success('导入成功');
      setImportOpen(false);
      loadData();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || '导入失败');
    } finally {
      setImportLoading(false);
    }
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: any) => (
        <Space>
          <ApartmentOutlined style={{ color: PRIMARY_COLOR }} />
          <a onClick={() => openDetail(record)}>{text}</a>
        </Space>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (t: string) => t || '-',
    },
    {
      title: '步骤数',
      dataIndex: 'step_count',
      key: 'step_count',
      width: 80,
      render: (n: number) => <Tag color="purple">{n || 0}</Tag>,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) =>
        tags && tags.length ? (
          tags.map((t) => <Tag key={t} color="blue">{t}</Tag>)
        ) : (
          '-'
        ),
    },
    {
      title: '使用次数',
      dataIndex: 'usage_count',
      key: 'usage_count',
      width: 90,
      render: (n: number) => (n || 0),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: any) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(record)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          </Tooltip>
          <Tooltip title="复制">
            <Button size="small" icon={<CopyOutlined />} onClick={() => handleDuplicate(record)} />
          </Tooltip>
          <Popconfirm
            title="确认删除该步骤组？"
            onConfirm={() => handleDelete(record)}
          >
            <Tooltip title="删除">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <ApartmentOutlined style={{ color: PRIMARY_COLOR }} />
          <span>步骤库（可复用步骤组）</span>
        </Space>
      }
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
          <Button icon={<ImportOutlined />} onClick={openImport}>从用例导入</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建步骤组
          </Button>
        </Space>
      }
    >
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear
          placeholder="按项目筛选"
          style={{ width: 200 }}
          value={filterProject}
          onChange={(v) => {
            setFilterProject(v);
            setPage(1);
            loadData(1, pageSize, v, search);
          }}
          options={projects.map((p) => ({ label: p.name, value: p.id }))}
        />
        <Input.Search
          allowClear
          placeholder="搜索名称/描述"
          style={{ width: 240 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onSearch={(v) => {
            setPage(1);
            loadData(1, pageSize, filterProject, v);
          }}
        />
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        size="middle"
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
        locale={{ emptyText: <Empty description="暂无步骤组，点击「新建步骤组」或「从用例导入」" /> }}
      />

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑步骤组' : '新建步骤组'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        width={680}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入步骤组名称' }]}
          >
            <Input placeholder="如：登录操作" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="步骤组的用途说明" />
          </Form.Item>
          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select
              mode="tags"
              placeholder="输入标签后回车"
              tokenSeparators={[',']}
            />
          </Form.Item>
          <Form.Item
            name="stepsText"
            label="步骤定义（JSON 数组）"
            tooltip="与 UI 用例 steps 格式一致，如 [{&quot;action&quot;:&quot;click&quot;,&quot;selector&quot;:&quot;#login&quot;}]；也可通过「从用例导入」快速生成"
            rules={[{ required: true, message: '请填写步骤 JSON' }]}
          >
            <Input.TextArea
              rows={10}
              style={{ fontFamily: 'monospace', fontSize: 12 }}
              placeholder='[{"action":"navigate","value":"https://example.com"},{"action":"input","selector":"#username","value":"admin"}]'
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情预览 Modal */}
      <Modal
        title={
          detail ? `步骤组详情：${detail.name}` : '步骤组详情'
        }
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={720}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>加载中...</div>
        ) : detail ? (
          <div>
            {detail.steps && detail.steps.length ? (
              <Table
                rowKey={(_r: any, i?: number) => String(i ?? 0)}
                dataSource={detail.steps}
                pagination={false}
                size="small"
                columns={[
                  {
                    title: '#',
                    width: 50,
                    render: (_: any, __: any, i: number) => i + 1,
                  },
                  {
                    title: '动作',
                    dataIndex: 'action',
                    width: 100,
                    render: (a: string) => (
                      <Tag color="geekblue">
                        {ACTION_LABELS[a] || a}
                      </Tag>
                    ),
                  },
                  {
                    title: '选择器',
                    dataIndex: 'selector',
                    render: (t: string) => t ? <code style={{ fontSize: 12 }}>{t}</code> : '-',
                  },
                  {
                    title: '值',
                    dataIndex: 'value',
                    render: (t: string) => t || '-',
                  },
                  {
                    title: '描述',
                    dataIndex: 'description',
                    render: (t: string) => t || '-',
                  },
                ]}
              />
            ) : (
              <Empty description="该步骤组暂无步骤" />
            )}
          </div>
        ) : (
          <Empty />
        )}
      </Modal>

      {/* 从用例导入 Modal */}
      <Modal
        title="从 UI 用例导入步骤组"
        open={importOpen}
        onOk={handleImport}
        onCancel={() => setImportOpen(false)}
        confirmLoading={importLoading}
        width={560}
        okText="导入"
        cancelText="取消"
      >
        <Form form={importForm} layout="vertical">
          <Form.Item
            name="case_id"
            label="选择 UI 用例"
            rules={[{ required: true, message: '请选择 UI 用例' }]}
          >
            <Select
              showSearch
              placeholder="选择用例"
              optionFilterProp="label"
              loading={importLoading}
              options={importCases.map((c: any) => ({
                label: `${c.title}（${(c.steps || []).length} 步）`,
                value: c.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label="步骤组名称"
            rules={[{ required: true, message: '请输入步骤组名称' }]}
          >
            <Input placeholder="如：登录操作" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="步骤组的用途说明" />
          </Form.Item>
          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
          <Space size="large">
            <Form.Item name="start_index" label="起始步骤索引（含）">
              <InputNumber min={0} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="end_index" label="结束步骤索引（不含，留空到末尾）">
              <InputNumber min={0} style={{ width: 200 }} placeholder="留空=到末尾" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Card>
  );
}
