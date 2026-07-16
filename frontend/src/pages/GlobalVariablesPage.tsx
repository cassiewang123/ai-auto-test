import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Space,
  message,
  Popconfirm,
  Tag,
  Card,
  Select,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { globalVariableApi, projectApi } from '../services/api';
import type { GlobalVariable, GlobalVariableCreate, Project } from '../types';

const { TextArea } = Input;

const VAR_TYPES = [
  { label: '字符串 (string)', value: 'string' },
  { label: '数字 (number)', value: 'number' },
  { label: '布尔 (boolean)', value: 'boolean' },
  { label: 'JSON', value: 'json' },
];

const SCOPES = [
  { label: '全局 (global)', value: 'global' },
  { label: '工作空间 (workspace)', value: 'workspace' },
];

// 作用域颜色
const scopeColor: Record<string, string> = {
  global: 'purple',
  workspace: 'blue',
};
// 变量类型颜色
const typeColor: Record<string, string> = {
  string: 'default',
  number: 'green',
  boolean: 'orange',
  json: 'geekblue',
};

export default function GlobalVariablesPage() {
  const [data, setData] = useState<GlobalVariable[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [scopeFilter, setScopeFilter] = useState<string>('');

  const [projects, setProjects] = useState<Project[]>([]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<GlobalVariable | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  async function loadData(p = page, ps = pageSize, kw = keyword, scope = scopeFilter) {
    setLoading(true);
    try {
      const params: any = { page: p, page_size: ps };
      if (kw) params.name = kw;
      if (scope) params.scope = scope;
      const res = await globalVariableApi.list(params);
      setData(res.data || []);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData(1);
    projectApi.listAll().then((res) => setProjects(res.data || [])).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      var_type: 'string',
      scope: 'global',
      value: '',
    });
    setModalOpen(true);
  }

  function openEdit(record: GlobalVariable) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      value: record.value,
      var_type: record.var_type,
      description: record.description,
      scope: record.scope,
      project_id: record.project_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values: any = await form.validateFields();
      // workspace 作用域校验项目
      if (values.scope === 'workspace' && !values.project_id) {
        message.warning('工作空间作用域必须选择项目');
        return;
      }
      setSubmitting(true);
      const payload: GlobalVariableCreate = {
        name: values.name,
        value: values.value ?? '',
        var_type: values.var_type,
        description: values.description,
        scope: values.scope,
        project_id: values.scope === 'workspace' ? values.project_id : undefined,
      };
      if (editing) {
        await globalVariableApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await globalVariableApi.create(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await globalVariableApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  const projectNameMap = new Map<string, Project>();
  projects.forEach((p) => projectNameMap.set(p.id, p));

  return (
    <div>
      <Card
        title={
          <Space>
            <GlobalOutlined />
            <span>变量管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              全局 / 工作空间变量，执行时按 临时 &gt; 环境 &gt; 全局 优先级合并
            </span>
          </Space>
        }
        extra={
          <Space>
            <Select
              placeholder="作用域筛选"
              allowClear
              style={{ width: 160 }}
              value={scopeFilter || undefined}
              onChange={(v) => {
                setScopeFilter(v || '');
                setPage(1);
                loadData(1, pageSize, keyword, v || '');
              }}
              options={SCOPES}
            />
            <Input.Search
              placeholder="搜索变量名"
              allowClear
              style={{ width: 220 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(v) => {
                setPage(1);
                loadData(1, pageSize, v, scopeFilter);
              }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建变量
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={data}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
              loadData(p, ps);
            },
          }}
          columns={[
            {
              title: '变量名',
              dataIndex: 'name',
              width: 200,
              render: (v: string) => (
                <code style={{ background: '#f3f4f6', padding: '2px 6px', borderRadius: 4, fontWeight: 600 }}>
                  {v}
                </code>
              ),
            },
            {
              title: '值',
              dataIndex: 'value',
              ellipsis: true,
              render: (v: string) => (
                <code style={{ color: '#374151' }}>{v || '(空)'}</code>
              ),
            },
            {
              title: '类型',
              dataIndex: 'var_type',
              width: 100,
              render: (v: string) => <Tag color={typeColor[v] || 'default'}>{v}</Tag>,
            },
            {
              title: '作用域',
              dataIndex: 'scope',
              width: 110,
              render: (v: string) => (
                <Tag color={scopeColor[v] || 'default'}>{v === 'global' ? '全局' : '工作空间'}</Tag>
              ),
            },
            {
              title: '所属项目',
              dataIndex: 'project_id',
              width: 140,
              render: (pid: string) =>
                pid ? projectNameMap.get(pid)?.name || pid : <span style={{ color: '#9ca3af' }}>-</span>,
            },
            {
              title: '描述',
              dataIndex: 'description',
              ellipsis: true,
              render: (v: string) => v || '-',
            },
            {
              title: '更新时间',
              dataIndex: 'updated_at',
              width: 180,
              render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
            },
            {
              title: '操作',
              width: 180,
              render: (_, record) => (
                <Space>
                  <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
                    编辑
                  </Button>
                  <Popconfirm title="确认删除该变量？" onConfirm={() => handleDelete(record.id)}>
                    <Button size="small" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? '编辑变量' : '新建变量'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="变量名"
            rules={[{ required: true, message: '请输入变量名' }]}
          >
            <Input placeholder="如：base_url、token" />
          </Form.Item>
          <Form.Item name="value" label="值">
            <TextArea rows={2} placeholder="变量值（json 类型请输入合法 JSON）" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="var_type" label="变量类型" style={{ width: 200 }}>
              <Select options={VAR_TYPES} />
            </Form.Item>
            <Form.Item name="scope" label="作用域" style={{ flex: 1, minWidth: 200 }}>
              <Select
                options={SCOPES}
                onChange={() => {
                  // 切换作用域时清空项目
                  const scope = form.getFieldValue('scope');
                  if (scope !== 'workspace') {
                    form.setFieldValue('project_id', undefined);
                  }
                }}
              />
            </Form.Item>
          </Space>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.scope !== cur.scope}>
            {({ getFieldValue }) =>
              getFieldValue('scope') === 'workspace' ? (
                <Form.Item
                  name="project_id"
                  label="所属项目"
                  rules={[{ required: true, message: '工作空间作用域必须选择项目' }]}
                >
                  <Select
                    placeholder="选择项目"
                    showSearch
                    optionFilterProp="label"
                    options={projects.map((p) => ({ label: p.name, value: p.id }))}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="变量说明（可选）" />
          </Form.Item>
          <div style={{ color: '#9ca3af', fontSize: 12 }}>
            变量在执行时通过 <code>{'${变量名}'}</code> 占位符引用。优先级：临时变量 &gt; 环境变量 &gt; 全局变量。
          </div>
        </Form>
      </Modal>
    </div>
  );
}
