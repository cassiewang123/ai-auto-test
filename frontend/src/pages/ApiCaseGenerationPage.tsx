import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  DeleteOutlined,
  ExperimentOutlined,
  ImportOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { aiApi, apiCaseRecordApi, projectApi, testCaseApi } from '../services/api';
import {
  buildKeyedCases,
  pickSelectedCases,
  toImportCases,
  type KeyedCase,
} from '../utils/generatedCaseSelection';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type InterfaceItem = {
  id: string;
  title: string;
  method: string;
  url: string;
  headers?: Record<string, any> | null;
  params?: Record<string, any> | null;
  body?: any;
  group_path?: string | null;
  project_id?: string | null;
};

type GeneratedCase = {
  title: string;
  case_type?: string;
  priority?: string;
  method?: string;
  url?: string;
  headers?: Record<string, any>;
  params?: Record<string, any>;
  body?: any;
  assertions?: Array<{ type?: string; expected?: any; assertion_type?: string }>;
  description?: string;
};

const METHOD_COLOR: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'purple',
  DELETE: 'red',
};

const CASE_TYPE_OPTIONS = [
  { label: '正常场景', value: 'normal' },
  { label: '异常场景', value: 'exception' },
  { label: '边界值', value: 'boundary' },
  { label: '权限校验', value: 'permission' },
];

const CASE_TYPE_LABEL: Record<string, string> = {
  normal: '正常',
  exception: '异常',
  boundary: '边界',
  permission: '权限',
};

const CASE_TYPE_COLOR: Record<string, string> = {
  normal: 'green',
  exception: 'volcano',
  boundary: 'gold',
  permission: 'purple',
};

function safeParse(text: string): { ok: boolean; value?: any; error?: string } {
  if (!text.trim()) return { ok: true, value: undefined };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e: any) {
    return { ok: false, error: e.message };
  }
}

export default function ApiCaseGenerationPage() {
  const navigate = useNavigate();
  const [interfaces, setInterfaces] = useState<InterfaceItem[]>([]);
  const [loadingInterfaces, setLoadingInterfaces] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [projects, setProjects] = useState<any[]>([]);
  const [targetProjectId, setTargetProjectId] = useState<string | null>(null);

  const [method, setMethod] = useState('POST');
  const [url, setUrl] = useState('');
  const [paramForm] = Form.useForm();
  const [bodyText, setBodyText] = useState('');
  const [headersText, setHeadersText] = useState('');

  const [caseTypes, setCaseTypes] = useState<string[]>(['normal', 'exception', 'boundary']);
  const [maxCases, setMaxCases] = useState(15);
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<KeyedCase<GeneratedCase>[]>([]);
  const [selectedRows, setSelectedRows] = useState<React.Key[]>([]);
  const [importing, setImporting] = useState(false);
  const [previewCase, setPreviewCase] = useState<GeneratedCase | null>(null);

  useEffect(() => {
    setLoadingInterfaces(true);
    testCaseApi
      .list({ page: 1, page_size: 500 })
      .then((res) => setInterfaces(res.data || []))
      .catch((e: any) => message.error(e.message))
      .finally(() => setLoadingInterfaces(false));
    projectApi
      .listAll()
      .then((res) => setProjects(res.data || []))
      .catch(() => {});
  }, []);

  const visibleInterfaces = useMemo(() => {
    if (!targetProjectId) return interfaces;
    return interfaces.filter(
      (item) => !item.project_id || item.project_id === targetProjectId
    );
  }, [interfaces, targetProjectId]);

  const selectedInterface = interfaces.find((item) => item.id === selectedId);

  function applyInterface(record: InterfaceItem) {
    setSelectedId(record.id);
    setMethod(record.method || 'POST');
    setUrl(record.url || '');
    const params = record.params && typeof record.params === 'object' ? record.params : {};
    paramForm.setFieldsValue({
      params: Object.entries(params).map(([key, value]) => ({
        key,
        value: typeof value === 'string' ? value : JSON.stringify(value),
      })),
    });
    setBodyText(record.body == null ? '' : JSON.stringify(record.body, null, 2));
    setHeadersText(
      record.headers && Object.keys(record.headers).length > 0
        ? JSON.stringify(record.headers, null, 2)
        : ''
    );
    setGenerated([]);
    setSelectedRows([]);
    if (record.project_id) setTargetProjectId(record.project_id);
  }

  function buildSourceData() {
    const formValues = paramForm.getFieldsValue();
    const params: Record<string, any> = {};
    (formValues.params || []).forEach((item: any) => {
      const key = (item?.key || '').trim();
      if (!key) return;
      // 数字与布尔值按原类型传入，其余按字符串
      const raw = item?.value ?? '';
      if (raw === 'true') params[key] = true;
      else if (raw === 'false') params[key] = false;
      else if (raw !== '' && !Number.isNaN(Number(raw))) params[key] = Number(raw);
      else params[key] = raw;
    });

    const body = safeParse(bodyText);
    if (!body.ok) throw new Error(`请求体不是合法 JSON：${body.error}`);
    const headers = safeParse(headersText);
    if (!headers.ok) throw new Error(`请求头不是合法 JSON：${headers.error}`);

    return {
      name: selectedInterface?.title,
      method,
      url,
      params,
      headers: headers.value || {},
      body: body.value ?? null,
    };
  }

  async function handleGenerate() {
    if (!selectedId) {
      message.warning('请先选择接口');
      return;
    }
    if (!url.trim()) {
      message.warning('接口地址不能为空');
      return;
    }
    if (caseTypes.length === 0) {
      message.warning('请至少选择一种场景类型');
      return;
    }

    let sourceData: Record<string, any>;
    try {
      sourceData = buildSourceData();
    } catch (e: any) {
      message.error(e.message);
      return;
    }

    setGenerating(true);
    try {
      const res = await aiApi.generateTestCases({
        source_type: 'interface',
        source_data: sourceData,
        options: { case_types: caseTypes, max_cases: maxCases },
      });
      const rows = buildKeyedCases<GeneratedCase>(res.data?.cases || []);
      setGenerated(rows);
      setSelectedRows(rows.map((row) => row.rowKey));
      message.success(`已生成 ${rows.length} 条接口测试用例`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleImport() {
    if (selectedRows.length === 0) {
      message.warning('请先选择要导入的用例');
      return;
    }
    setImporting(true);
    try {
      // 选中项保存的是表格行键，必须按行键匹配；直接拿它当数组下标会取到
      // undefined，提交后后端只会报「cases.0: Input should be a valid dictionary」。
      const picked = pickSelectedCases(generated, selectedRows);
      const cases = toImportCases(picked);
      if (cases.length === 0) {
        message.warning('选中的用例已失效，请重新生成后再导入');
        setSelectedRows([]);
        return;
      }
      // 导入到「用例管理」的接口用例库，而不是直接进入可执行的接口管理
      const res = await apiCaseRecordApi.bulkImport({
        cases,
        project_id: targetProjectId || selectedInterface?.project_id || null,
        interface_name: selectedInterface?.title || null,
        group_path: selectedInterface?.group_path || null,
      });
      message.success(
        `已导入 ${res.data?.created_count ?? cases.length} 条接口用例到「用例管理」`
      );
      navigate('/api-case-management');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setImporting(false);
    }
  }

  const columns = [
    {
      title: '用例标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (value: string, record: GeneratedCase) => (
        <a onClick={() => setPreviewCase(record)}>{value}</a>
      ),
    },
    {
      title: '场景',
      dataIndex: 'case_type',
      width: 90,
      render: (value: string) => (
        <Tag color={CASE_TYPE_COLOR[value] || 'default'}>
          {CASE_TYPE_LABEL[value] || value || '-'}
        </Tag>
      ),
    },
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (value: string) => (
        <Tag color={METHOD_COLOR[value] || 'default'}>{value}</Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (value: string) => <Tag>{value || '-'}</Tag>,
    },
    {
      title: '预期状态码',
      width: 100,
      render: (_: unknown, record: GeneratedCase) => {
        const status = record.assertions?.find(
          (item) => (item.type || item.assertion_type) === 'status_code'
        );
        return status?.expected ?? '-';
      },
    },
  ];

  return (
    <Row gutter={16}>
      <Col xs={24} xl={10}>
        <Card
          title={
            <Space>
              <ExperimentOutlined />
              <span>接口用例生成</span>
            </Space>
          }
          size="small"
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="选择接口并填写传参，按正常/异常/边界/权限场景自动生成接口测试用例"
          />

          <Row gutter={12}>
            <Col span={14}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                选择接口
              </Text>
              <Select
                showSearch
                allowClear
                loading={loadingInterfaces}
                placeholder="搜索接口名称或 URL"
                style={{ width: '100%' }}
                value={selectedId}
                optionFilterProp="label"
                onChange={(value) => {
                  const record = interfaces.find((item) => item.id === value);
                  if (record) applyInterface(record);
                }}
                options={visibleInterfaces.map((item) => ({
                  value: item.id,
                  label: `${item.method} ${item.title} · ${item.url}`,
                }))}
              />
            </Col>
            <Col span={10}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                导入到项目（可选）
              </Text>
              <Select
                allowClear
                style={{ width: '100%' }}
                placeholder="跟随接口所属项目"
                value={targetProjectId || undefined}
                onChange={(value) => setTargetProjectId(value || null)}
                options={projects.map((project) => ({
                  value: project.id,
                  label: project.name,
                }))}
              />
            </Col>
          </Row>

          <Divider style={{ margin: '12px 0' }} />

          <Row gutter={12}>
            <Col span={7}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                方法
              </Text>
              <Select
                value={method}
                onChange={setMethod}
                style={{ width: '100%' }}
                options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Col>
            <Col span={17}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                接口地址
              </Text>
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="/api/v1/xxx" />
            </Col>
          </Row>

          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              查询参数（传参）
            </Text>
            <Form form={paramForm} initialValues={{ params: [] }}>
              <Form.List name="params">
                {(fields, { add, remove }) => (
                  <>
                    {fields.map((field) => (
                      <Space key={field.key} align="baseline" style={{ display: 'flex' }}>
                        <Form.Item {...field} name={[field.name, 'key']} noStyle>
                          <Input placeholder="参数名" style={{ width: 170 }} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'value']} noStyle>
                          <Input placeholder="参数值" style={{ width: 230 }} />
                        </Form.Item>
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => remove(field.name)}
                        />
                      </Space>
                    ))}
                    <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({ key: '', value: '' })}>
                      添加参数
                    </Button>
                  </>
                )}
              </Form.List>
            </Form>
          </div>

          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              请求体 JSON
            </Text>
            <TextArea
              rows={5}
              value={bodyText}
              onChange={(e) => setBodyText(e.target.value)}
              placeholder='{"username": "test"}'
            />
          </div>

          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              请求头 JSON（可选）
            </Text>
            <TextArea
              rows={2}
              value={headersText}
              onChange={(e) => setHeadersText(e.target.value)}
              placeholder='{"Content-Type": "application/json"}'
            />
          </div>

          <Divider style={{ margin: '12px 0' }} />

          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                生成场景
              </Text>
              <Checkbox.Group
                value={caseTypes}
                onChange={(values) => setCaseTypes(values as string[])}
                options={CASE_TYPE_OPTIONS}
              />
            </div>
            <Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                最多生成
              </Text>
              <InputNumber min={1} max={100} value={maxCases} onChange={(v) => setMaxCases(v || 10)} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                条
              </Text>
            </Space>
            <Button
              type="primary"
              block
              icon={<ThunderboltOutlined />}
              loading={generating}
              onClick={handleGenerate}
            >
              生成接口用例
            </Button>
          </Space>
        </Card>
      </Col>

      <Col xs={24} xl={14}>
        <Card
          size="small"
          title={`生成结果（${generated.length}）`}
          extra={
            <Space>
              <Button
                size="small"
                onClick={() => setSelectedRows(generated.map((row) => row.rowKey))}
                disabled={generated.length === 0}
              >
                全选
              </Button>
              <Button
                size="small"
                onClick={() => setSelectedRows([])}
                disabled={generated.length === 0}
              >
                取消选择
              </Button>
              <Button
                type="primary"
                size="small"
                icon={<ImportOutlined />}
                loading={importing}
                disabled={selectedRows.length === 0}
                onClick={handleImport}
              >
                导入用例管理（{selectedRows.length}）
              </Button>
            </Space>
          }
        >
          {generated.length === 0 ? (
            <Empty description="选择接口、填写参数后点击「生成接口用例」" style={{ padding: 40 }} />
          ) : (
            <Table
              rowKey="rowKey"
              size="small"
              dataSource={generated}
              columns={columns}
              rowSelection={{
                selectedRowKeys: selectedRows,
                onChange: (keys) => setSelectedRows(keys),
              }}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              expandable={{
                expandedRowRender: (record: GeneratedCase) => (
                  <div style={{ paddingLeft: 8 }}>
                    <Paragraph style={{ marginBottom: 4 }}>
                      <Text strong>请求：</Text>
                      <Tag color={METHOD_COLOR[record.method || 'GET']}>{record.method}</Tag>
                      <Text code>{record.url}</Text>
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 4 }}>
                      <Text strong>参数：</Text>
                      <Text code>{JSON.stringify(record.params || {})}</Text>
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 4 }}>
                      <Text strong>请求体：</Text>
                      <Text code>{JSON.stringify(record.body ?? null)}</Text>
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 0 }}>
                      <Text strong>断言：</Text>
                      <Text code>{JSON.stringify(record.assertions || [])}</Text>
                    </Paragraph>
                  </div>
                ),
              }}
            />
          )}
        </Card>

        {previewCase && (
          <Card size="small" title="用例详情" style={{ marginTop: 12 }}>
            <Tooltip title="点击「生成结果」中的标题查看">
              <Text strong>{previewCase.title}</Text>
            </Tooltip>
            <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 12 }}>
              {JSON.stringify(previewCase, null, 2)}
            </pre>
          </Card>
        )}
      </Col>
    </Row>
  );
}
