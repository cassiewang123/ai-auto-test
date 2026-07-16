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
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  BugOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { knowledgeApi } from '../services/api';

const { TextArea } = Input;

// 缺陷类型选项
const PATTERN_TYPE_OPTIONS = [
  { label: '错误', value: 'error' },
  { label: '边界', value: 'boundary' },
  { label: '安全', value: 'security' },
  { label: '性能', value: 'performance' },
  { label: '逻辑', value: 'logic' },
];

// 缺陷类型对应的 Tag 颜色
const PATTERN_TYPE_COLOR: Record<string, string> = {
  error: 'red',
  boundary: 'orange',
  security: 'volcano',
  performance: 'purple',
  logic: 'blue',
};

// 严重等级选项
const SEVERITY_OPTIONS = [
  { label: 'P0', value: 'P0' },
  { label: 'P1', value: 'P1' },
  { label: 'P2', value: 'P2' },
];

const SEVERITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'orange',
  P2: 'blue',
};

// 将 pattern_content 对象序列化为字符串用于编辑
function stringifyContent(content: any): string {
  if (content === null || content === undefined) return '';
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return '';
  }
}

export default function DefectPatternsPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [patternType, setPatternType] = useState<string | undefined>(undefined);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  // 提取弹窗
  const [extractOpen, setExtractOpen] = useState(false);
  const [extractId, setExtractId] = useState('');
  const [extracting, setExtracting] = useState(false);

  async function loadData(p = page, ps = pageSize, pt = patternType) {
    setLoading(true);
    try {
      const res = await knowledgeApi.listDefects({
        page: p,
        page_size: ps,
        pattern_type: pt,
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
    loadData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      pattern_type: 'error',
      severity: 'P2',
      pattern_content: '',
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      pattern_type: record.pattern_type,
      severity: record.severity,
      description: record.description,
      pattern_content: stringifyContent(record.pattern_content),
      project_id: record.project_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      // 解析 pattern_content JSON
      let patternContent: any = values.pattern_content;
      if (typeof patternContent === 'string' && patternContent.trim()) {
        try {
          patternContent = JSON.parse(patternContent);
        } catch {
          message.error('pattern_content 不是合法的 JSON');
          setSubmitting(false);
          return;
        }
      }
      const payload: any = {
        name: values.name,
        pattern_type: values.pattern_type,
        severity: values.severity,
        description: values.description,
        pattern_content: patternContent || {},
      };
      if (values.project_id) payload.project_id = values.project_id;

      if (editing) {
        await knowledgeApi.updateDefect(editing.id, payload);
        message.success('更新成功');
      } else {
        await knowledgeApi.createDefect(payload);
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
      await knowledgeApi.deleteDefect(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 客户端按名称过滤（后端列表接口暂不支持名称搜索）
  const filteredData = keyword
    ? data.filter((item) =>
        (item.name || '').toLowerCase().includes(keyword.toLowerCase())
      )
    : data;

  async function handleExtract() {
    if (!extractId.trim()) {
      message.warning('请输入测试结果 ID');
      return;
    }
    setExtracting(true);
    try {
      await knowledgeApi.extractDefect(extractId.trim());
      message.success('提取成功');
      setExtractOpen(false);
      setExtractId('');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setExtracting(false);
    }
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <BugOutlined />
            <span>缺陷模式库</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 条
            </span>
          </Space>
        }
        extra={
          <Space wrap>
            <Input.Search
              placeholder="搜索名称"
              allowClear
              style={{ width: 200 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(v) => setKeyword(v)}
            />
            <Select
              allowClear
              placeholder="缺陷类型"
              style={{ width: 140 }}
              options={PATTERN_TYPE_OPTIONS}
              value={patternType}
              onChange={(v) => {
                setPatternType(v);
                setPage(1);
                loadData(1, pageSize, v);
              }}
            />
            <Button
              icon={<ExperimentOutlined />}
              onClick={() => setExtractOpen(true)}
            >
              从测试结果提取
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={filteredData}
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
              title: '名称',
              dataIndex: 'name',
              width: 180,
              render: (v: string) => (
                <span style={{ fontWeight: 600 }}>{v}</span>
              ),
            },
            {
              title: '缺陷类型',
              dataIndex: 'pattern_type',
              width: 110,
              render: (v: string) => {
                const opt = PATTERN_TYPE_OPTIONS.find((o) => o.value === v);
                return (
                  <Tag color={PATTERN_TYPE_COLOR[v] || 'default'}>
                    {opt ? opt.label : v || '-'}
                  </Tag>
                );
              },
            },
            {
              title: '严重等级',
              dataIndex: 'severity',
              width: 90,
              render: (v: string) =>
                v ? (
                  <Tag color={SEVERITY_COLOR[v] || 'default'}>{v}</Tag>
                ) : (
                  '-'
                ),
            },
            {
              title: '出现次数',
              dataIndex: 'occurrence_count',
              width: 90,
              render: (v: number) => v ?? 0,
            },
            {
              title: '描述',
              dataIndex: 'description',
              ellipsis: true,
              render: (v: string) => v || '-',
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 180,
              render: (t: string) =>
                t ? new Date(t).toLocaleString('zh-CN') : '-',
            },
            {
              title: '操作',
              width: 180,
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
                    title="确认删除该缺陷模式？"
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
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editing ? '编辑缺陷模式' : '新建缺陷模式'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={620}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：空指针异常" />
          </Form.Item>
          <Form.Item
            name="pattern_type"
            label="缺陷类型"
            rules={[{ required: true, message: '请选择缺陷类型' }]}
          >
            <Select options={PATTERN_TYPE_OPTIONS} placeholder="选择类型" />
          </Form.Item>
          <Form.Item
            name="severity"
            label="严重等级"
            rules={[{ required: true, message: '请选择严重等级' }]}
          >
            <Select options={SEVERITY_OPTIONS} placeholder="选择等级" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="缺陷模式描述（可选）" />
          </Form.Item>
          <Form.Item
            name="pattern_content"
            label="模式内容（JSON）"
            tooltip="请输入合法 JSON，如匹配规则、特征字段等"
          >
            <TextArea
              rows={6}
              placeholder='{\n  "keywords": ["null", "NPE"],\n  "regex": "NullPointerException"\n}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item name="project_id" label="项目 ID（可选）">
            <Input placeholder="关联项目 ID，留空表示全局" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 从测试结果提取弹窗 */}
      <Modal
        title="从测试结果提取缺陷模式"
        open={extractOpen}
        onOk={handleExtract}
        confirmLoading={extracting}
        onCancel={() => {
          setExtractOpen(false);
          setExtractId('');
        }}
        okText="提取"
        width={520}
        destroyOnClose
      >
        <p style={{ color: '#6b7280', marginBottom: 12 }}>
          输入测试结果（TestResult）ID，系统将从其 AI 归因分析结果中提取缺陷模式。
        </p>
        <Input
          placeholder="请输入 TestResult ID"
          value={extractId}
          onChange={(e) => setExtractId(e.target.value)}
          onPressEnter={handleExtract}
        />
      </Modal>
    </div>
  );
}
