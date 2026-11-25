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
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Tree,
  Typography,
  message,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import {
  DeleteOutlined,
  ExperimentOutlined,
  FolderOpenOutlined,
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
import {
  buildGroupSelectOptions,
  buildGroupTree,
  isUnderGroup,
  normalizeGroupPath,
} from '../utils/apiModules';

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
  /** 按模块批量生成时，标记该用例来自哪个接口/模块 */
  interface_name?: string;
  group_path?: string;
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

/** 生成范围：单个接口 / 整个模块 */
type ScopeMode = 'single' | 'module';

function safeParse(text: string): { ok: boolean; value?: any; error?: string } {
  if (!text.trim()) return { ok: true, value: undefined };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e: any) {
    return { ok: false, error: e.message };
  }
}

/** 统计某模块（含其下子模块）的接口数量，用于模块下拉展示 */
function countInterfacesUnder(
  interfaces: readonly InterfaceItem[],
  groupPath: string
): number {
  return interfaces.filter((item) => isUnderGroup(item.group_path, groupPath))
    .length;
}

export default function ApiCaseGenerationPage() {
  const navigate = useNavigate();
  const [interfaces, setInterfaces] = useState<InterfaceItem[]>([]);
  const [loadingInterfaces, setLoadingInterfaces] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [projects, setProjects] = useState<any[]>([]);
  const [targetProjectId, setTargetProjectId] = useState<string | null>(null);

  // 生成范围：单接口保留原有表单，模块范围按模块批量生成
  const [scope, setScope] = useState<ScopeMode>('single');
  const [selectedGroupPath, setSelectedGroupPath] = useState<string>('');
  // 空字符串同时表示「未分组」，需要一个独立标记区分「还没选模块」
  const [modulePicked, setModulePicked] = useState(false);
  const [moduleCaseTypes, setModuleCaseTypes] = useState<string[]>([
    'normal',
    'exception',
    'boundary',
  ]);
  const [moduleMaxPerInterface, setModuleMaxPerInterface] = useState(5);
  const [moduleProgress, setModuleProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);

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

  // ---- 模块（分组）视图 ----
  const moduleTree = useMemo(
    () => buildGroupTree(visibleInterfaces, [], { includeUngrouped: true }),
    [visibleInterfaces]
  );

  const moduleSelectOptions = useMemo(() => {
    const options = buildGroupSelectOptions(
      visibleInterfaces.map((item) => item.group_path || '')
    );
    const ungroupedCount = visibleInterfaces.filter(
      (item) => !normalizeGroupPath(item.group_path)
    ).length;
    return [
      ...options.map((option) => ({
        value: option.value,
        label: `${option.display}（${countInterfacesUnder(visibleInterfaces, option.value)}）`,
      })),
      ...(ungroupedCount > 0
        ? [{ value: '', label: `未分组（${ungroupedCount}）` }]
        : []),
    ];
  }, [visibleInterfaces]);

  /** 当前模块下的接口（含其下子模块）；未选模块时为空 */
  const moduleInterfaces = useMemo(() => {
    if (scope !== 'module' || !modulePicked) return [];
    return visibleInterfaces.filter((item) =>
      isUnderGroup(item.group_path, selectedGroupPath)
    );
  }, [scope, modulePicked, selectedGroupPath, visibleInterfaces]);

  const moduleTreeData = useMemo<DataNode[]>(() => {
    function toDataNode(node: (typeof moduleTree)[number]): DataNode {
      return {
        key: node.path === '' ? '__ungrouped__' : node.path,
        title: (
          <Space size={4}>
            <FolderOpenOutlined style={{ color: node.path ? '#d97706' : '#9ca3af' }} />
            <span>{node.name}</span>
            <Tag style={{ marginInlineEnd: 0 }}>{node.totalCount}</Tag>
          </Space>
        ),
        children: node.children.map(toDataNode),
      };
    }
    return moduleTree.map(toDataNode);
  }, [moduleTree]);

  function handleTreeSelect(selectedKeys: React.Key[]) {
    const key = String(selectedKeys[0] ?? '');
    if (!key) {
      // 再次点击同一节点会取消选中：回到「未选择模块」状态
      setModulePicked(false);
      setSelectedGroupPath('');
    } else {
      setSelectedGroupPath(key === '__ungrouped__' ? '' : key);
      setModulePicked(true);
    }
    setGenerated([]);
    setSelectedRows([]);
  }

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

  /**
   * 按模块批量生成：把模块（含子模块）下每个接口逐个送 AI 生成，
   * 结果合并到同一张表里，并带上来源接口与模块，导入后即可按模块查看。
   */
  async function handleGenerateByModule() {
    if (moduleInterfaces.length === 0) {
      message.warning('当前模块下没有接口，请先选择有接口的模块');
      return;
    }
    if (moduleCaseTypes.length === 0) {
      message.warning('请至少选择一种场景类型');
      return;
    }

    setGenerating(true);
    setModuleProgress({ done: 0, total: moduleInterfaces.length });
    const collected: GeneratedCase[] = [];
    const failed: string[] = [];

    for (const [index, record] of moduleInterfaces.entries()) {
      try {
        const res = await aiApi.generateTestCases({
          source_type: 'interface',
          source_data: {
            name: record.title,
            method: record.method || 'POST',
            url: record.url || '',
            params: record.params || {},
            headers: record.headers || {},
            body: record.body ?? null,
          },
          options: {
            case_types: moduleCaseTypes,
            max_cases: moduleMaxPerInterface,
          },
        });
        (res.data?.cases || []).forEach((item: GeneratedCase) => {
          collected.push({
            ...item,
            // 用于导入时按用例归属到正确接口/模块
            interface_name: record.title,
            group_path: normalizeGroupPath(record.group_path) || undefined,
          });
        });
      } catch (e: any) {
        failed.push(`${record.title}（${e.message}）`);
      } finally {
        setModuleProgress({ done: index + 1, total: moduleInterfaces.length });
      }
    }

    const rows = buildKeyedCases<GeneratedCase>(collected);
    setGenerated(rows);
    setSelectedRows(rows.map((row) => row.rowKey));
    setModuleProgress(null);
    setGenerating(false);

    if (rows.length === 0) {
      message.error(
        failed.length > 0
          ? `生成失败：${failed.slice(0, 3).join('；')}`
          : '当前模块没有生成出用例，请调整场景类型或上限后重试'
      );
      return;
    }
    message.success(
      `已按模块「${selectedGroupPath || '未分组'}」生成 ${rows.length} 条用例（${moduleInterfaces.length} 个接口）`
    );    if (failed.length > 0) {
      message.warning(`${failed.length} 个接口生成失败：${failed.slice(0, 3).join('；')}`);
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
      // 导入到「用例管理」的接口用例库，而不是直接进入可执行的接口管理。
      // 模块生成时每条用例已自带 interface_name/group_path，后端按用例粒度落库；
      // 单接口生成时用例没有这两项，回落到请求级字段。
      const res = await apiCaseRecordApi.bulkImport({
        cases,
        project_id:
          targetProjectId ||
          selectedInterface?.project_id ||
          moduleInterfaces[0]?.project_id ||
          null,
        interface_name: scope === 'single' ? selectedInterface?.title || null : null,
        group_path: scope === 'single' ? selectedInterface?.group_path || null : null,
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
    // 模块批量生成时展示来源接口与模块，单接口生成时不占位
    ...(scope === 'module'
      ? [
          {
            title: '来源接口',
            dataIndex: 'interface_name',
            width: 180,
            ellipsis: true,
            render: (value: string, record: GeneratedCase) => (
              <Tooltip title={record.group_path || '未分组'}>
                <span>{value || '-'}</span>
              </Tooltip>
            ),
          },
        ]
      : []),
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
            message={
              scope === 'single'
                ? '选择接口并填写传参，按正常/异常/边界/权限场景自动生成接口测试用例'
                : '选择模块（分组），对模块下所有接口逐个生成用例，导入后按模块归档'
            }
          />

          <Segmented<ScopeMode>
            value={scope}
            onChange={(value) => {
              setScope(value);
              setGenerated([]);
              setSelectedRows([]);
            }}
            options={[
              { label: '按单个接口', value: 'single' },
              { label: '按模块（分组）', value: 'module' },
            ]}
            style={{ marginBottom: 12 }}
          />

          <Row gutter={12}>
            <Col span={14}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {scope === 'single' ? '选择接口' : '选择模块'}
              </Text>
              {scope === 'single' ? (
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
              ) : (
                <Select
                  showSearch
                  allowClear
                  loading={loadingInterfaces}
                  placeholder="选择模块，父级模块包含其下子模块"
                  style={{ width: '100%' }}
                  value={modulePicked ? selectedGroupPath : undefined}
                  optionFilterProp="label"
                  onChange={(value) => {
                    if (value === undefined || value === null) {
                      // 清空选择后回到「未选择模块」
                      setSelectedGroupPath('');
                      setModulePicked(false);
                    } else {
                      setSelectedGroupPath(value);
                      setModulePicked(true);
                    }
                    setGenerated([]);
                    setSelectedRows([]);
                  }}
                  options={moduleSelectOptions}
                />
              )}
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

          {scope === 'module' && (
            <div style={{ marginTop: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                模块目录（点击选择）
              </Text>
              <div
                style={{
                  maxHeight: 220,
                  overflow: 'auto',
                  border: '1px solid #f0f0f0',
                  borderRadius: 6,
                  padding: 8,
                  marginTop: 4,
                }}
              >
                {moduleTreeData.length === 0 ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    接口还没有分组信息，可先在「接口管理」里维护分组
                  </Text>
                ) : (
                  <Tree
                    treeData={moduleTreeData}
                    selectedKeys={
                      modulePicked
                        ? [selectedGroupPath === '' ? '__ungrouped__' : selectedGroupPath]
                        : []
                    }
                    onSelect={handleTreeSelect}
                    defaultExpandAll
                    blockNode
                  />
                )}
              </div>
              <Space style={{ marginTop: 8 }} wrap>
                {modulePicked ? (
                  <>
                    <Tag color="blue">
                      当前模块接口：{moduleInterfaces.length} 个
                    </Tag>
                    <Tag>模块路径：{selectedGroupPath || '未分组'}</Tag>
                  </>
                ) : (
                  <Tag>请选择模块</Tag>
                )}
              </Space>
            </div>
          )}

          <Divider style={{ margin: '12px 0' }} />

          {scope === 'single' ? (
            <>
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
            </>
          ) : (
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  生成场景（对模块内每个接口生效）
                </Text>
                <Checkbox.Group
                  value={moduleCaseTypes}
                  onChange={(values) => setModuleCaseTypes(values as string[])}
                  options={CASE_TYPE_OPTIONS}
                />
              </div>
              <Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  每个接口最多生成
                </Text>
                <InputNumber
                  min={1}
                  max={50}
                  value={moduleMaxPerInterface}
                  onChange={(v) => setModuleMaxPerInterface(v || 5)}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  条
                </Text>
              </Space>
              <Alert
                type="warning"
                showIcon={false}
                message={
                  modulePicked
                    ? `将逐个调用 ${moduleInterfaces.length} 个接口生成用例，接口较多时耗时较长`
                    : '请先在左侧「模块目录」或上方下拉框选择模块'
                }
                style={{ padding: '4px 8px', fontSize: 12 }}
              />
              {moduleProgress && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  生成进度：{moduleProgress.done}/{moduleProgress.total}
                </Text>
              )}
              <Button
                type="primary"
                block
                icon={<ThunderboltOutlined />}
                loading={generating}
                disabled={moduleInterfaces.length === 0}
                onClick={handleGenerateByModule}
              >
                按模块生成用例（{moduleInterfaces.length} 个接口）
              </Button>
            </Space>
          )}
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
            <Empty
              description={
                scope === 'single'
                  ? '选择接口、填写参数后点击「生成接口用例」'
                  : '选择模块后点击「按模块生成用例」，会对其下所有接口逐一生成'
              }
              style={{ padding: 40 }}
            />
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
