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
  InputNumber,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SolutionOutlined,
  RiseOutlined,
} from '@ant-design/icons';
import { knowledgeApi } from '../services/api';

const { TextArea } = Input;

// 规则类型选项
const RULE_TYPE_OPTIONS = [
  { label: '校验', value: 'validation' },
  { label: '业务流程', value: 'business_flow' },
  { label: '数据完整性', value: 'data_integrity' },
  { label: '安全', value: 'security' },
];

const RULE_TYPE_COLOR: Record<string, string> = {
  validation: 'blue',
  business_flow: 'cyan',
  data_integrity: 'geekblue',
  security: 'volcano',
};

// 优先级选项
const PRIORITY_OPTIONS = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
];

const PRIORITY_COLOR: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
};

// 将 rule_content 对象序列化为字符串用于编辑
function stringifyContent(content: any): string {
  if (content === null || content === undefined) return '';
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return '';
  }
}

export default function BusinessRulesPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [ruleType, setRuleType] = useState<string | undefined>(undefined);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  // 升级弹窗
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [threshold, setThreshold] = useState(3);
  const [promoting, setPromoting] = useState(false);

  async function loadData(p = page, ps = pageSize, rt = ruleType) {
    setLoading(true);
    try {
      const res = await knowledgeApi.listRules({
        page: p,
        page_size: ps,
        rule_type: rt,
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
      rule_type: 'validation',
      priority: 'medium',
      rule_content: '',
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      rule_type: record.rule_type,
      priority: record.priority,
      description: record.description,
      rule_content: stringifyContent(record.rule_content),
      project_id: record.project_id,
    });
    setModalOpen(true);
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      // 解析 rule_content JSON
      let ruleContent: any = values.rule_content;
      if (typeof ruleContent === 'string' && ruleContent.trim()) {
        try {
          ruleContent = JSON.parse(ruleContent);
        } catch {
          message.error('rule_content 不是合法的 JSON');
          setSubmitting(false);
          return;
        }
      }
      const payload: any = {
        name: values.name,
        rule_type: values.rule_type,
        priority: values.priority,
        description: values.description,
        rule_content: ruleContent || {},
      };
      if (values.project_id) payload.project_id = values.project_id;

      if (editing) {
        await knowledgeApi.updateRule(editing.id, payload);
        message.success('更新成功');
      } else {
        await knowledgeApi.createRule(payload);
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
      await knowledgeApi.deleteRule(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 客户端按名称过滤
  const filteredData = keyword
    ? data.filter((item) =>
        (item.name || '').toLowerCase().includes(keyword.toLowerCase())
      )
    : data;

  async function handlePromote() {
    setPromoting(true);
    try {
      const res = await knowledgeApi.promoteRules(threshold);
      const count = res?.data?.promoted_count ?? 0;
      message.success(`升级成功，共生成 ${count} 条业务规则`);
      setPromoteOpen(false);
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setPromoting(false);
    }
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <SolutionOutlined />
            <span>业务规则库</span>
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
              placeholder="规则类型"
              style={{ width: 140 }}
              options={RULE_TYPE_OPTIONS}
              value={ruleType}
              onChange={(v) => {
                setRuleType(v);
                setPage(1);
                loadData(1, pageSize, v);
              }}
            />
            <Button
              icon={<RiseOutlined />}
              onClick={() => setPromoteOpen(true)}
            >
              升级高频缺陷
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
              width: 200,
              render: (v: string) => (
                <span style={{ fontWeight: 600 }}>{v}</span>
              ),
            },
            {
              title: '规则类型',
              dataIndex: 'rule_type',
              width: 120,
              render: (v: string) => {
                const opt = RULE_TYPE_OPTIONS.find((o) => o.value === v);
                return (
                  <Tag color={RULE_TYPE_COLOR[v] || 'default'}>
                    {opt ? opt.label : v || '-'}
                  </Tag>
                );
              },
            },
            {
              title: '优先级',
              dataIndex: 'priority',
              width: 90,
              render: (v: string) => {
                const opt = PRIORITY_OPTIONS.find((o) => o.value === v);
                return v ? (
                  <Tag color={PRIORITY_COLOR[v] || 'default'}>
                    {opt ? opt.label : v}
                  </Tag>
                ) : (
                  '-'
                );
              },
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
                    title="确认删除该业务规则？"
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
        title={editing ? '编辑业务规则' : '新建业务规则'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：登录态校验规则" />
          </Form.Item>
          <Form.Item
            name="rule_type"
            label="规则类型"
            rules={[{ required: true, message: '请选择规则类型' }]}
          >
            <Select options={RULE_TYPE_OPTIONS} placeholder="选择类型" />
          </Form.Item>
          <Form.Item
            name="priority"
            label="优先级"
            rules={[{ required: true, message: '请选择优先级' }]}
          >
            <Select options={PRIORITY_OPTIONS} placeholder="选择优先级" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="业务规则描述（可选）" />
          </Form.Item>
          <Form.Item
            name="rule_content"
            label="规则内容（JSON）"
            tooltip="请输入合法 JSON，如校验逻辑、断言条件等"
          >
            <TextArea
              rows={6}
              placeholder='{\n  "field": "username",\n  "condition": "not_empty",\n  "message": "用户名不能为空"\n}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item name="project_id" label="项目 ID（可选）">
            <Input placeholder="关联项目 ID，留空表示全局" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 升级高频缺陷弹窗 */}
      <Modal
        title="升级高频缺陷为业务规则"
        open={promoteOpen}
        onOk={handlePromote}
        confirmLoading={promoting}
        onCancel={() => setPromoteOpen(false)}
        okText="执行升级"
        width={480}
        destroyOnHidden
      >
        <p style={{ color: '#6b7280', marginBottom: 12 }}>
          将出现次数超过阈值的缺陷模式自动升级为业务规则。
        </p>
        <Space orientation="vertical" style={{ width: '100%' }}>
          <span>出现次数阈值（大于该值才会被升级）</span>
          <InputNumber
            min={1}
            value={threshold}
            onChange={(v) => setThreshold(v ?? 3)}
            style={{ width: '100%' }}
          />
        </Space>
      </Modal>
    </div>
  );
}
