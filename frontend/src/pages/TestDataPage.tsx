import { useEffect, useState, useCallback, useMemo } from 'react';
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
  Radio,
  message,
  Popconfirm,
  Tooltip,
  Alert,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { apiClient, testCaseApi, environmentApi } from '../services/api';

const { TextArea } = Input;

// ========== 类型定义 ==========
interface TestDataSet {
  id: string;
  name: string;
  description?: string;
  format: 'csv' | 'json';
  data: string;
  variables: string[];
  test_case_id: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

interface ExecutionRowResult {
  row_index: number;
  input_data: Record<string, any>;
  status: string;
  duration: number;
  status_code: number | null;
  assertion_results: any[];
  error_message: string | null;
  url: string;
}

interface ExecutionResult {
  total: number;
  passed: number;
  failed: number;
  results: ExecutionRowResult[];
}

interface TestCaseOption {
  id: string;
  title: string;
  method: string;
  url: string;
}

interface EnvironmentOption {
  id: string;
  name: string;
  base_url: string;
}

// ========== 本地 API（不能修改 api.ts，在此定义） ==========
const testDataApi = {
  list: (params?: { test_case_id?: string; page?: number; page_size?: number }) =>
    apiClient.get('/test-data', { params }),
  get: (id: string) => apiClient.get(`/test-data/${id}`),
  create: (data: any) => apiClient.post('/test-data', data),
  update: (id: string, data: any) => apiClient.put(`/test-data/${id}`, data),
  delete: (id: string) => apiClient.delete(`/test-data/${id}`),
  preview: (id: string) => apiClient.post(`/test-data/${id}/preview`),
  execute: (data: any) => apiClient.post('/test-data/execute', data),
};

// ========== 客户端解析辅助函数 ==========
function parseCsvClient(text: string): { variables: string[]; rows: Record<string, string>[] } {
  if (!text || !text.trim()) return { variables: [], rows: [] };
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length === 0) return { variables: [], rows: [] };
  // 简单 CSV 解析（不支持引号内换行，足够预览用）
  const parseLine = (line: string): string[] => {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuotes && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch === ',' && !inQuotes) {
        result.push(current);
        current = '';
      } else {
        current += ch;
      }
    }
    result.push(current);
    return result;
  };
  const headers = parseLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const values = parseLine(line);
    const row: Record<string, string> = {};
    headers.forEach((h, i) => {
      row[h] = values[i] ?? '';
    });
    return row;
  });
  return { variables: headers, rows };
}

function parseJsonClient(text: string): { variables: string[]; rows: Record<string, any>[] } {
  if (!text || !text.trim()) return { variables: [], rows: [] };
  try {
    const data = JSON.parse(text);
    if (!Array.isArray(data)) return { variables: [], rows: [] };
    const variables: string[] = [];
    const seen = new Set<string>();
    data.forEach((item) => {
      if (item && typeof item === 'object') {
        Object.keys(item).forEach((k) => {
          if (!seen.has(k)) {
            seen.add(k);
            variables.push(k);
          }
        });
      }
    });
    return { variables, rows: data };
  } catch {
    return { variables: [], rows: [] };
  }
}

// ========== 状态颜色 ==========
const statusColor: Record<string, string> = {
  passed: 'green',
  failed: 'red',
  error: 'orange',
};

// ========== 主组件 ==========
export default function TestDataPage() {
  const [dataSets, setDataSets] = useState<TestDataSet[]>([]);
  const [testCases, setTestCases] = useState<TestCaseOption[]>([]);
  const [environments, setEnvironments] = useState<EnvironmentOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string>('');

  // 创建/编辑 Modal
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editing, setEditing] = useState<TestDataSet | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [formData, setFormData] = useState<{ format: 'csv' | 'json'; data: string }>({
    format: 'csv',
    data: '',
  });

  // 执行 Modal
  const [execModalOpen, setExecModalOpen] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<ExecutionResult | null>(null);
  const [execEnvId, setExecEnvId] = useState<string>('');
  const [execDataSetId, setExecDataSetId] = useState<string>('');

  // 加载测试用例列表
  const loadTestCases = useCallback(async () => {
    try {
      const res = await testCaseApi.list({ page: 1, page_size: 200 });
      const items = (res.data || []) as TestCaseOption[];
      setTestCases(items);
      if (items.length > 0 && !selectedCaseId) {
        setSelectedCaseId(items[0].id);
      }
    } catch (e: any) {
      message.error(e.message);
    }
  }, [selectedCaseId]);

  // 加载环境列表
  const loadEnvironments = useCallback(async () => {
    try {
      const res = await environmentApi.list({ page: 1, page_size: 100 });
      setEnvironments((res.data || []) as EnvironmentOption[]);
    } catch {
      // 环境列表加载失败不阻塞
    }
  }, []);

  // 加载数据集
  const loadDataSets = useCallback(async () => {
    if (!selectedCaseId) {
      setDataSets([]);
      return;
    }
    setLoading(true);
    try {
      const res = await testDataApi.list({ test_case_id: selectedCaseId, page: 1, page_size: 100 });
      setDataSets((res.data || []) as TestDataSet[]);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedCaseId]);

  useEffect(() => {
    loadTestCases();
    loadEnvironments();
  }, [loadTestCases, loadEnvironments]);

  useEffect(() => {
    loadDataSets();
  }, [loadDataSets]);

  // 实时预览
  const preview = useMemo(() => {
    if (!formData.data.trim()) return { variables: [] as string[], rows: [] as any[] };
    return formData.format === 'csv'
      ? parseCsvClient(formData.data)
      : parseJsonClient(formData.data);
  }, [formData]);

  // 打开创建 Modal
  function openCreate() {
    setEditing(null);
    form.resetFields();
    const init = { format: 'csv' as const, data: 'username,password\nalice,1234\nbob,5678' };
    form.setFieldsValue(init);
    setFormData(init);
    setEditModalOpen(true);
  }

  // 打开编辑 Modal
  function openEdit(record: TestDataSet) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      format: record.format,
      data: record.data,
      is_active: record.is_active,
    });
    setFormData({ format: record.format, data: record.data });
    setEditModalOpen(true);
  }

  // 提交创建/编辑
  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editing) {
        await testDataApi.update(editing.id, values);
        message.success('更新成功');
      } else {
        await testDataApi.create({ ...values, test_case_id: selectedCaseId });
        message.success('创建成功');
      }
      setEditModalOpen(false);
      loadDataSets();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  // 删除
  async function handleDelete(id: string) {
    try {
      await testDataApi.delete(id);
      message.success('删除成功');
      loadDataSets();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 打开执行 Modal
  function openExecute() {
    setExecResult(null);
    setExecEnvId('');
    setExecDataSetId('');
    setExecModalOpen(true);
  }

  // 执行数据驱动测试
  async function handleExecute() {
    if (!selectedCaseId) {
      message.warning('请先选择测试用例');
      return;
    }
    setExecuting(true);
    try {
      const payload: any = { test_case_id: selectedCaseId };
      if (execEnvId) payload.environment_id = execEnvId;

      // 选了具体数据集则只执行该数据集，否则执行所有启用的数据集
      const targetSets = execDataSetId
        ? dataSets.filter((d) => d.id === execDataSetId)
        : dataSets.filter((d) => d.is_active);

      if (targetSets.length === 0) {
        message.warning('没有可执行的数据集');
        setExecuting(false);
        return;
      }

      const results: ExecutionRowResult[] = [];
      let totalPassed = 0;
      let totalFailed = 0;
      for (const ds of targetSets) {
        const res = await testDataApi.execute({ ...payload, data_set_id: ds.id });
        const result = res.data as ExecutionResult;
        results.push(...result.results);
        totalPassed += result.passed;
        totalFailed += result.failed;
      }
      setExecResult({
        total: results.length,
        passed: totalPassed,
        failed: totalFailed,
        results,
      });
      message.success(`执行完成：${totalPassed} 通过，${totalFailed} 失败`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setExecuting(false);
    }
  }

  // 预览列
  const previewColumns = useMemo(() => {
    return preview.variables.map((v) => ({
      title: v,
      dataIndex: v,
      ellipsis: true,
      width: 120,
    }));
  }, [preview.variables]);

  return (
    <div>
      {/* 顶部：选择测试用例 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>关联测试用例：</span>
          <Select
            style={{ width: 400 }}
            showSearch
            placeholder="选择测试用例"
            value={selectedCaseId || undefined}
            onChange={(v) => setSelectedCaseId(v)}
            optionFilterProp="label"
            options={testCases.map((c) => ({
              label: `[${c.method}] ${c.title}`,
              value: c.id,
            }))}
          />
          <Button icon={<ReloadOutlined />} onClick={loadDataSets}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreate}
            disabled={!selectedCaseId}
          >
            新建数据集
          </Button>
          <Button
            icon={<PlayCircleOutlined />}
            onClick={openExecute}
            disabled={dataSets.length === 0}
          >
            数据驱动执行
          </Button>
        </Space>
      </Card>

      {/* 数据集表格 */}
      <Table
        dataSource={dataSets}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
        columns={[
          { title: '名称', dataIndex: 'name', width: 180 },
          {
            title: '格式',
            dataIndex: 'format',
            width: 80,
            render: (v: string) => (
              <Tag color={v === 'csv' ? 'blue' : 'geekblue'}>
                {v.toUpperCase()}
              </Tag>
            ),
          },
          {
            title: '变量',
            dataIndex: 'variables',
            width: 120,
            render: (vars: string[]) => (
              <Tooltip title={vars.join(', ')}>
                <span>{vars.length} 个变量</span>
              </Tooltip>
            ),
          },
          {
            title: '数据行数',
            width: 100,
            render: (_, record) => {
              const parsed =
                record.format === 'csv'
                  ? parseCsvClient(record.data)
                  : parseJsonClient(record.data);
              return parsed.rows.length;
            },
          },
          {
            title: '状态',
            dataIndex: 'is_active',
            width: 80,
            render: (v: boolean) =>
              v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>,
          },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 180,
            render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
          },
          {
            title: '操作',
            width: 200,
            render: (_, record) => (
              <Space>
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
        title={editing ? '编辑数据集' : '新建数据集'}
        open={editModalOpen}
        onOk={handleSubmit}
        onCancel={() => setEditModalOpen(false)}
        width={800}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入数据集名称' }]}
          >
            <Input placeholder="如：登录测试数据" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="数据集描述（可选）" />
          </Form.Item>
          <Form.Item
            name="format"
            label="格式"
            rules={[{ required: true }]}
          >
            <Radio.Group
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, format: e.target.value }))
              }
            >
              <Radio.Button value="csv">CSV</Radio.Button>
              <Radio.Button value="json">JSON</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item
            name="data"
            label="数据内容"
            rules={[{ required: true, message: '请输入数据内容' }]}
            extra={
              formData.format === 'csv'
                ? 'CSV 格式：第一行为表头（变量名），后续每行为一条数据'
                : 'JSON 格式：对象数组，每个对象的键为变量名'
            }
          >
            <TextArea
              rows={10}
              placeholder={
                formData.format === 'csv'
                  ? 'username,password\nalice,1234\nbob,5678'
                  : '[\n  {"username": "alice", "password": "1234"},\n  {"username": "bob", "password": "5678"}\n]'
              }
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, data: e.target.value }))
              }
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>

          {/* 实时预览 */}
          {preview.variables.length > 0 && (
            <div>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 8 }}
                message={`解析到 ${preview.variables.length} 个变量：${preview.variables.join(', ')}`}
              />
              <Table
                dataSource={preview.rows.slice(0, 5)}
                rowKey={(_, idx) => String(idx)}
                size="small"
                pagination={false}
                scroll={{ x: 'max-content' }}
                columns={previewColumns}
              />
              {preview.rows.length > 5 && (
                <div style={{ textAlign: 'center', color: '#999', marginTop: 4 }}>
                  共 {preview.rows.length} 行，仅显示前 5 行
                </div>
              )}
            </div>
          )}
        </Form>
      </Modal>

      {/* 执行 Modal */}
      <Modal
        title="数据驱动执行"
        open={execModalOpen}
        onCancel={() => setExecModalOpen(false)}
        footer={
          <Space>
            <Button onClick={() => setExecModalOpen(false)}>关闭</Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={executing}
              onClick={handleExecute}
            >
              执行
            </Button>
          </Space>
        }
        width={1000}
        destroyOnClose
      >
        {!execResult ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Alert
              type="info"
              showIcon
              message={`将对用例下 ${dataSets.filter((d) => d.is_active).length} 个启用的数据集执行数据驱动测试`}
            />
            <div>
              <span style={{ marginRight: 8 }}>选择数据集：</span>
              <Select
                style={{ width: 320 }}
                allowClear
                placeholder="不选则执行所有启用的数据集"
                value={execDataSetId || undefined}
                onChange={(v) => setExecDataSetId(v || '')}
                options={dataSets.map((d) => ({
                  label: `${d.name} (${d.format.toUpperCase()})`,
                  value: d.id,
                }))}
              />
            </div>
            <div>
              <span style={{ marginRight: 8 }}>执行环境（可选）：</span>
              <Select
                style={{ width: 320 }}
                allowClear
                placeholder="选择环境（可选）"
                value={execEnvId || undefined}
                onChange={(v) => setExecEnvId(v || '')}
                options={environments.map((e) => ({
                  label: `${e.name} (${e.base_url})`,
                  value: e.id,
                }))}
              />
            </div>
          </Space>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Space size="large">
              <Tag color="blue">总计 {execResult.total}</Tag>
              <Tag color="green">通过 {execResult.passed}</Tag>
              <Tag color="red">失败 {execResult.failed}</Tag>
            </Space>
            <Table
              dataSource={execResult.results}
              rowKey="row_index"
              size="small"
              pagination={{ pageSize: 10 }}
              scroll={{ x: 'max-content' }}
              columns={[
                {
                  title: '#',
                  dataIndex: 'row_index',
                  width: 50,
                  render: (v: number) => v + 1,
                },
                {
                  title: '输入数据',
                  dataIndex: 'input_data',
                  ellipsis: true,
                  width: 250,
                  render: (data: Record<string, any>) => (
                    <Tooltip
                      title={<pre style={{ margin: 0 }}>{JSON.stringify(data, null, 2)}</pre>}
                    >
                      <code style={{ fontSize: 12 }}>
                        {JSON.stringify(data)}
                      </code>
                    </Tooltip>
                  ),
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 80,
                  render: (v: string) => (
                    <Tag color={statusColor[v] || 'default'}>{v}</Tag>
                  ),
                },
                {
                  title: 'HTTP状态',
                  dataIndex: 'status_code',
                  width: 90,
                  render: (v: number | null) => v ?? '-',
                },
                {
                  title: '耗时(s)',
                  dataIndex: 'duration',
                  width: 90,
                  render: (v: number) => v.toFixed(4),
                },
                {
                  title: '错误信息',
                  dataIndex: 'error_message',
                  ellipsis: true,
                  render: (v: string | null) => v ?? '-',
                },
              ]}
            />
          </Space>
        )}
      </Modal>
    </div>
  );
}
