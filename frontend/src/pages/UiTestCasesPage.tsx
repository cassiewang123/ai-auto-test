import { useEffect, useState, useRef, useMemo } from 'react';
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
  Timeline,
  Statistic,
  Row,
  Col,
  Spin,
  Image,
  List,
  Collapse,
  Radio,
  Upload,
  InputNumber,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  MinusCircleOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CameraOutlined,
  VideoCameraOutlined,
  StopOutlined,
  SaveOutlined,
  PictureOutlined,
  UploadOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { uiTestCaseApi, projectApi, visualRegressionApi, uiTestRecordApi, stepLibraryApi } from '../services/api';
import type { Project } from '../types';

const browserColor: Record<string, string> = {
  chrome: 'blue',
  firefox: 'orange',
  edge: 'cyan',
};

const BROWSERS = ['chrome', 'firefox', 'edge'];

// UI 测试步骤支持的动作类型
const ACTIONS = [
  'navigate', 'click', 'input', 'assert', 'wait', 'screenshot',
  'select', 'press', 'hover', 'drag', 'scroll', 'upload', 'download',
];

// 动作中文名映射，便于在编辑器下拉中显示
const ACTION_LABELS: Record<string, string> = {
  navigate: 'navigate / 导航',
  click: 'click / 点击',
  input: 'input / 输入',
  assert: 'assert / 断言',
  wait: 'wait / 等待',
  screenshot: 'screenshot / 截图',
  select: 'select / 选择',
  press: 'press / 按键',
  hover: 'hover / 悬停',
  drag: 'drag / 拖拽',
  scroll: 'scroll / 滚动',
  upload: 'upload / 上传',
  download: 'download / 下载',
  step_group: 'step_group / 步骤组引用',
};

interface UiTestStep {
  action: string;
  selector?: string;
  value?: string;
  description?: string;
  source?: string;       // drag 起始元素
  target?: string;       // drag 目标元素
  direction?: string;    // scroll 方向 up/down
  amount?: number;       // scroll 像素数
  file_path?: string;    // upload 文件路径
  save_path?: string;    // download 保存路径
  step_library_id?: string;  // step_group 引用的步骤组 ID
}

export default function UiTestCasesPage() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [projects, setProjects] = useState<Project[]>([]);
  const [filterProject, setFilterProject] = useState<string | undefined>(undefined);
  const [titleSearch, setTitleSearch] = useState('');
  const [viewMode, setViewMode] = useState<'flat' | 'grouped'>('flat');

  // 新建/编辑
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [form] = Form.useForm();

  // 运行结果
  const [resultOpen, setResultOpen] = useState(false);
  const [runResult, setRunResult] = useState<any>(null);

  // 录制功能
  const [recordOpen, setRecordOpen] = useState(false);
  const [recordStep, setRecordStep] = useState<'config' | 'recording' | 'review'>('config');
  const [recordUrl, setRecordUrl] = useState('');
  const [recordBrowser, setRecordBrowser] = useState('chrome');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recordEvents, setRecordEvents] = useState<any[]>([]);
  const [recordLoading, setRecordLoading] = useState(false);
  const [recordStopping, setRecordStopping] = useState(false);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveProjectId, setSaveProjectId] = useState<string | undefined>(undefined);
  const [savingRecording, setSavingRecording] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 视觉基线管理
  const [baselineOpen, setBaselineOpen] = useState(false);
  const [baselineCase, setBaselineCase] = useState<any>(null);
  const [baselines, setBaselines] = useState<any[]>([]);
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [newBaselineName, setNewBaselineName] = useState('');
  const [newBaselineThreshold, setNewBaselineThreshold] = useState(0.1);
  const [newBaselineImage, setNewBaselineImage] = useState<string | null>(null);
  const [savingBaseline, setSavingBaseline] = useState(false);

  // 步骤组（Page Object Model）选择器与预览
  const [stepGroupPickerOpen, setStepGroupPickerOpen] = useState(false);
  const [stepGroupList, setStepGroupList] = useState<any[]>([]);
  const [stepGroupLoading, setStepGroupLoading] = useState(false);
  const [stepGroupSearch, setStepGroupSearch] = useState('');
  // 步骤组子步骤预览
  const [stepGroupPreviewOpen, setStepGroupPreviewOpen] = useState(false);
  const [stepGroupPreview, setStepGroupPreview] = useState<any>(null);
  const [stepGroupPreviewLoading, setStepGroupPreviewLoading] = useState(false);
  // 保存 Form.List 的 add 函数引用，供步骤组选择器回调使用
  const addStepRef = useRef<((step: any) => void) | null>(null);

  async function loadData(
    p = page,
    ps = pageSize,
    projectId = filterProject,
    title = titleSearch
  ) {
    setLoading(true);
    try {
      const res = await uiTestCaseApi.list({
        page: p,
        page_size: ps,
        project_id: projectId,
        title_search: title,
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

  // 计算按项目分组的数据
  const groupedData = useMemo(() => {
    const groups: Record<string, { projectName: string; cases: any[] }> = {};
    // 初始化所有项目
    projects.forEach((p) => {
      groups[p.id] = { projectName: p.name, cases: [] };
    });
    groups['ungrouped'] = { projectName: '未分组', cases: [] };
    // 分配用例
    data.forEach((item) => {
      const key = item.project_id || 'ungrouped';
      if (groups[key]) {
        groups[key].cases.push(item);
      } else {
        groups['ungrouped'].cases.push(item);
      }
    });
    return groups;
  }, [data, projects]);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      browser_type: 'chrome',
      steps: [{ action: 'navigate' }],
      is_active: true,
      retry_count: 0,
      retry_interval: 2.0,
    });
    setModalOpen(true);
  }

  function openEdit(record: any) {
    setEditing(record);
    form.setFieldsValue({
      title: record.title,
      url: record.url,
      browser_type: record.browser_type,
      description: record.description,
      project_id: record.project_id,
      steps:
        record.steps && record.steps.length > 0
          ? record.steps
          : [{ action: 'navigate' }],
      is_active: record.is_active ?? true,
      retry_count: record.retry_count ?? 0,
      retry_interval: record.retry_interval ?? 2.0,
    });
    setModalOpen(true);
  }

  // 打开步骤组选择器：加载步骤库列表
  async function openStepGroupPicker(addFn: (step: any) => void) {
    addStepRef.current = addFn;
    setStepGroupSearch('');
    setStepGroupPickerOpen(true);
    setStepGroupLoading(true);
    try {
      const res = await stepLibraryApi.list({ page: 1, page_size: 100 });
      setStepGroupList(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setStepGroupLoading(false);
    }
  }

  // 重新搜索步骤组
  async function searchStepGroups(kw: string) {
    setStepGroupSearch(kw);
    setStepGroupLoading(true);
    try {
      const res = await stepLibraryApi.list({ page: 1, page_size: 100, search: kw || undefined });
      setStepGroupList(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setStepGroupLoading(false);
    }
  }

  // 选择步骤组后插入一条 step_group 步骤
  function insertStepGroup(group: any) {
    if (addStepRef.current) {
      addStepRef.current({
        action: 'step_group',
        step_library_id: group.id,
        description: group.name,
      });
      message.success(`已插入步骤组：${group.name}`);
    }
    setStepGroupPickerOpen(false);
  }

  // 预览步骤组的子步骤
  async function previewStepGroup(stepLibraryId: string, fallbackName?: string) {
    setStepGroupPreviewOpen(true);
    setStepGroupPreview({ name: fallbackName || '步骤组', steps: [] });
    setStepGroupPreviewLoading(true);
    try {
      const res = await stepLibraryApi.expand(stepLibraryId);
      setStepGroupPreview(res.data);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setStepGroupPreviewLoading(false);
    }
  }

  async function handleSubmit() {
    try {
      const values = await form.validateFields();
      setSaving(true);
      // 根据动作类型保留对应字段，避免向后台传递无关字段
      const steps: UiTestStep[] = (values.steps || []).map((s: any) => {
        const step: UiTestStep = {
          action: s.action,
          description: s.description,
        };
        switch (s.action) {
          case 'navigate':
            step.value = s.value;
            break;
          case 'click':
          case 'input':
          case 'assert':
          case 'select':
          case 'press':
          case 'hover':
            step.selector = s.selector;
            step.value = s.value;
            break;
          case 'wait':
            step.value = s.value;
            break;
          case 'screenshot':
            // 截图无参数
            break;
          case 'drag':
            step.source = s.source;
            step.target = s.target;
            break;
          case 'scroll':
            step.selector = s.selector;
            step.direction = s.direction || 'down';
            step.amount = Number(s.amount) || 500;
            break;
          case 'upload':
            step.selector = s.selector;
            step.file_path = s.file_path;
            break;
          case 'download':
            step.selector = s.selector;
            step.save_path = s.save_path;
            break;
          case 'step_group':
            // 步骤组引用：保留 step_library_id
            step.step_library_id = s.step_library_id;
            break;
          default:
            step.selector = s.selector;
            step.value = s.value;
        }
        return step;
      });
      const payload: any = {
        title: values.title,
        url: values.url,
        browser_type: values.browser_type,
        description: values.description,
        project_id: values.project_id || null,
        steps,
        is_active: values.is_active ?? true,
        retry_count: values.retry_count ?? 0,
        retry_interval: values.retry_interval ?? 2.0,
      };
      if (editing) {
        await uiTestCaseApi.update(editing.id, payload);
        message.success('更新成功');
      } else {
        await uiTestCaseApi.create(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await uiTestCaseApi.delete(id);
      message.success('删除成功');
      loadData();
    } catch (e: any) {
      message.error(e.message);
    }
  }

  async function handleRun(record: any) {
    setRunning(record.id);
    try {
      const res = await uiTestCaseApi.run(record.id);
      const result = res?.data;
      setRunResult(result);
      setResultOpen(true);
      if (result?.status === 'passed') {
        message.success(`UI 测试通过 (${result.passed_steps}/${result.total_steps} 步骤)`);
      } else if (result?.status === 'failed') {
        message.warning(`UI 测试失败: ${result.error || ''}`);
      } else {
        message.error(`UI 测试错误: ${result?.error || '未知错误'}`);
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRunning(null);
    }
  }

  const columns = [
    { title: '标题', dataIndex: 'title', width: 180, ellipsis: true },
    { title: '起始 URL', dataIndex: 'url', width: 220, ellipsis: true },
    {
      title: '浏览器类型',
      dataIndex: 'browser_type',
      width: 110,
      render: (b: string) => (
        <Tag color={browserColor[b] || 'default'}>{b || '-'}</Tag>
      ),
    },
    {
      title: '步骤数',
      dataIndex: 'steps',
      width: 80,
      align: 'center' as const,
      render: (steps: any[]) => (steps ? steps.length : 0),
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
      width: 160,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      width: 330,
      render: (_: any, record: any) => (
        <Space wrap>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<PlayCircleOutlined />}
            loading={running === record.id}
            onClick={() => handleRun(record)}
            data-testid="run-ui-case-btn"
          >
            运行
          </Button>
          <Button
            size="small"
            icon={<PictureOutlined />}
            onClick={() => openBaselines(record)}
          >
            基线
          </Button>
          <Popconfirm
            title="确认删除该 UI 用例？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 渲染运行结果 Modal 内容
  function renderResultContent() {
    if (!runResult) return <Empty description="暂无结果" />;

    const status = runResult.status;
    const statusColor =
      status === 'passed' ? '#52c41a' : status === 'failed' ? '#ff4d4f' : '#faad14';
    const statusText =
      status === 'passed' ? '通过' : status === 'failed' ? '失败' : '错误';

    return (
      <div>
        {/* 统计概览 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="执行状态"
                value={statusText}
                valueStyle={{ color: statusColor, fontWeight: 700 }}
                prefix={
                  status === 'passed' ? <CheckCircleOutlined /> : <CloseCircleOutlined />
                }
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="通过 / 总步骤"
                value={`${runResult.passed_steps || 0} / ${runResult.total_steps || 0}`}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="执行耗时"
                value={runResult.duration || 0}
                precision={2}
                suffix="s"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="浏览器"
                value={runResult.browser_type || '-'}
              />
            </Card>
          </Col>
        </Row>

        {/* 重试记录：有多次尝试时展示 */}
        {runResult.retry_attempts && runResult.retry_attempts.length > 1 && (
          <Card
            size="small"
            title={
              <Space>
                <ReloadOutlined style={{ color: '#4f46e5' }} />
                <span>重试记录</span>
                {runResult.status === 'passed' && (
                  <Tag color="green">
                    第 {runResult.final_attempt} 次尝试成功
                  </Tag>
                )}
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Timeline
              items={runResult.retry_attempts.map((a: any, i: number) => ({
                key: i,
                color: a.status === 'passed' ? 'green' : 'red',
                dot:
                  a.status === 'passed' ? (
                    <CheckCircleOutlined style={{ fontSize: 14, color: '#52c41a' }} />
                  ) : (
                    <CloseCircleOutlined style={{ fontSize: 14, color: '#ff4d4f' }} />
                  ),
                children: (
                  <div style={{ fontSize: 13 }}>
                    <span style={{ fontWeight: 600 }}>
                      第 {a.attempt} 次尝试
                    </span>
                    <Tag
                      color={a.status === 'passed' ? 'green' : 'red'}
                      style={{ marginLeft: 8 }}
                    >
                      {a.status === 'passed' ? '通过' : '失败'}
                    </Tag>
                    <span style={{ color: '#8c8c8c', marginLeft: 8 }}>
                      耗时 {a.duration}s
                    </span>
                    {a.error && (
                      <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 2 }}>
                        {a.error}
                      </div>
                    )}
                  </div>
                ),
              }))}
            />
          </Card>
        )}

        {/* 错误信息 */}
        {runResult.error && (
          <div
            style={{
              background: '#fff2f0',
              border: '1px solid #ffccc7',
              borderRadius: 6,
              padding: '8px 12px',
              marginBottom: 16,
            }}
          >
            <span style={{ color: '#ff4d4f', fontWeight: 600 }}>错误信息: </span>
            <span style={{ color: '#5c0011' }}>{runResult.error}</span>
          </div>
        )}

        {/* 步骤执行时间线 */}
        {runResult.steps && runResult.steps.length > 0 && (
          <Card
            size="small"
            title="步骤执行详情"
            style={{ marginBottom: 16 }}
          >
            <Timeline
              items={runResult.steps.map((s: any, i: number) => ({
                key: i,
                color: s.status === 'passed' ? 'green' : 'red',
                dot:
                  s.status === 'passed' ? (
                    <CheckCircleOutlined style={{ fontSize: 16, color: '#52c41a' }} />
                  ) : (
                    <CloseCircleOutlined style={{ fontSize: 16, color: '#ff4d4f' }} />
                  ),
                children: (
                  <div>
                    <div style={{ fontWeight: 600 }}>
                      步骤 {s.step}: {s.action}
                      {s.selector ? ` → ${s.selector}` : ''}
                      {s.value ? ` = "${s.value}"` : ''}
                    </div>
                    {s.description && (
                      <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                        {s.description}
                      </div>
                    )}
                    {s.message && (
                      <div style={{ color: '#595959', fontSize: 12, marginTop: 2 }}>
                        {s.message}
                      </div>
                    )}
                    {s.error && (
                      <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 2 }}>
                        {s.error}
                      </div>
                    )}
                    <div style={{ color: '#bfbfbf', fontSize: 11, marginTop: 2 }}>
                      耗时: {s.duration}s
                    </div>
                  </div>
                ),
              }))}
            />
          </Card>
        )}

        {/* 截图展示 */}
        {runResult.screenshots && runResult.screenshots.length > 0 && (
          <Card
            size="small"
            title={
              <Space>
                <CameraOutlined />
                <span>执行截图 ({runResult.screenshots.length})</span>
              </Space>
            }
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              {runResult.screenshots.map((screenshot: string, idx: number) => (
                <div key={idx} style={{ textAlign: 'center' }}>
                  <Image
                    src={`data:image/png;base64,${screenshot}`}
                    alt={`截图 ${idx + 1}`}
                    width={240}
                    style={{ borderRadius: 6, border: '1px solid #d9d9d9' }}
                  />
                  <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                    截图 {idx + 1}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* 视觉回归对比结果 */}
        {runResult.visual_diff && (
          <Card
            size="small"
            title={
              <Space>
                <PictureOutlined />
                <span>视觉回归对比结果</span>
                {runResult.visual_diff.passed ? (
                  <Tag color="green">通过</Tag>
                ) : (
                  <Tag color="red">差异超阈值</Tag>
                )}
              </Space>
            }
            style={{ marginTop: 16 }}
          >
            <Row gutter={16} style={{ marginBottom: 12 }}>
              <Col span={8}>
                <Statistic
                  title="差异分数"
                  value={runResult.visual_diff.diff_score}
                  precision={4}
                  valueStyle={{
                    color: runResult.visual_diff.passed ? '#52c41a' : '#ff4d4f',
                  }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="阈值"
                  value={runResult.visual_diff.threshold}
                  precision={2}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="基线名称"
                  value={runResult.visual_diff.baseline_name || '-'}
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
            </Row>
            {runResult.visual_diff.diff_image && (
              <div>
                <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>
                  差异图（红色区域为差异像素）：
                </div>
                <Image
                  src={`data:image/png;base64,${runResult.visual_diff.diff_image}`}
                  alt="视觉差异图"
                  width={480}
                  style={{ borderRadius: 6, border: '1px solid #d9d9d9' }}
                />
              </div>
            )}
          </Card>
        )}
      </div>
    );
  }

  // ===================== 录制功能 =====================

  function openRecording() {
    setRecordStep('config');
    setRecordUrl('');
    setRecordBrowser('chrome');
    setSessionId(null);
    setRecordEvents([]);
    setRecordError(null);
    setSaveTitle('');
    setSaveProjectId(undefined);
    setRecordOpen(true);
  }

  function closeRecording() {
    // 如果正在录制，先停止
    if (sessionId && recordStep === 'recording') {
      stopRecording();
    }
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
    setRecordOpen(false);
  }

  async function startRecording() {
    if (!recordUrl.trim()) {
      message.warning('请输入目标 URL');
      return;
    }
    setRecordLoading(true);
    setRecordError(null);
    try {
      const res = await uiTestCaseApi.startRecording({
        url: recordUrl,
        browser_type: recordBrowser,
      });
      const sid = res.data?.session_id;
      if (!sid) {
        message.error('启动录制失败');
        return;
      }
      setSessionId(sid);
      setRecordStep('recording');
      setRecordEvents([]);
      message.success('浏览器已启动，请在弹出的浏览器窗口中进行操作');

      // 开始轮询事件
      pollTimer.current = setInterval(async () => {
        if (!sid) return;
        try {
          const evRes = await uiTestCaseApi.getRecordingEvents(sid);
          const d = evRes.data;
          if (d) {
            setRecordEvents(d.events || []);
            if (d.status === 'error') {
              setRecordError(d.error || '录制出错');
              if (pollTimer.current) {
                clearInterval(pollTimer.current);
                pollTimer.current = null;
              }
            }
          }
        } catch {
          // 轮询失败，忽略
        }
      }, 2000);
    } catch (e: any) {
      message.error(e.message);
      setRecordError(e.message);
    } finally {
      setRecordLoading(false);
    }
  }

  async function stopRecording() {
    if (!sessionId) return;
    setRecordStopping(true);
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
    try {
      const res = await uiTestCaseApi.stopRecording(sessionId);
      const steps = res.data?.steps || [];
      setRecordEvents(steps);
      setRecordStep('review');
      setSaveTitle(`录制用例-${dayjs().format('MMDDHHmm')}`);
      message.success(`录制完成，共捕获 ${steps.length} 个步骤`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setRecordStopping(false);
    }
  }

  async function saveRecording() {
    if (!saveTitle.trim()) {
      message.warning('请输入用例标题');
      return;
    }
    if (recordEvents.length === 0) {
      message.warning('没有可保存的步骤');
      return;
    }
    setSavingRecording(true);
    try {
      // 直接用已有步骤创建用例，不再依赖已过期的录制会话
      await uiTestCaseApi.create({
        title: saveTitle,
        url: recordUrl,
        browser_type: recordBrowser,
        steps: recordEvents,
        project_id: saveProjectId || null,
        is_active: true,
      });
      message.success(`保存成功，共 ${recordEvents.length} 个步骤`);
      setRecordOpen(false);
      loadData();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSavingRecording(false);
    }
  }

  // ===================== 视觉基线管理 =====================

  async function openBaselines(record: any) {
    setBaselineCase(record);
    setBaselineOpen(true);
    setNewBaselineName(`${record.title}-基线-${dayjs().format('MMDDHHmm')}`);
    setNewBaselineThreshold(0.1);
    setNewBaselineImage(null);
    await loadBaselines(record.id);
  }

  async function loadBaselines(caseId: string) {
    setBaselineLoading(true);
    try {
      const res = await visualRegressionApi.listBaselines({
        case_id: caseId,
        page: 1,
        page_size: 50,
      });
      setBaselines(res.data || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBaselineLoading(false);
    }
  }

  // 从最近一次执行记录的最终截图设置基线
  async function setBaselineFromLatestRun() {
    if (!baselineCase) return;
    try {
      // 取该用例最近一条执行记录
      const recRes = await uiTestRecordApi.list({
        page: 1,
        page_size: 1,
        case_id: baselineCase.id,
      });
      const latestRecord = recRes.data?.[0];
      if (!latestRecord) {
        message.warning('该用例暂无执行记录，请先运行一次');
        return;
      }
      // 从执行结果拿不到截图，截图在 run 接口返回。这里改用 run 接口最新结果
      const runRes = await uiTestCaseApi.run(baselineCase.id);
      const screenshots = runRes?.data?.screenshots || [];
      if (screenshots.length === 0) {
        message.warning('执行未产生截图，无法设置基线');
        return;
      }
      setNewBaselineImage(screenshots[screenshots.length - 1]);
      setNewBaselineName(
        `${baselineCase.title}-基线-${dayjs().format('MMDDHHmm')}`
      );
      message.success('已从最新执行截图获取基线图片，点击"保存基线"确认');
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 处理上传图片：转为 base64
  function handleUploadImage(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      setNewBaselineImage(reader.result as string);
      message.success('图片已加载，点击"保存基线"确认');
    };
    reader.readAsDataURL(file);
    return false; // 阻止 antd 自动上传
  }

  async function saveBaseline() {
    if (!baselineCase) return;
    if (!newBaselineName.trim()) {
      message.warning('请输入基线名称');
      return;
    }
    if (!newBaselineImage) {
      message.warning('请上传基线图片或从最近执行截图获取');
      return;
    }
    setSavingBaseline(true);
    try {
      await visualRegressionApi.createBaseline({
        ui_test_case_id: baselineCase.id,
        name: newBaselineName,
        baseline_image: newBaselineImage,
        threshold: newBaselineThreshold,
      });
      message.success('基线保存成功');
      setNewBaselineImage(null);
      setNewBaselineName('');
      await loadBaselines(baselineCase.id);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSavingBaseline(false);
    }
  }

  async function deleteBaseline(id: string) {
    try {
      await visualRegressionApi.deleteBaseline(id);
      message.success('删除成功');
      if (baselineCase) await loadBaselines(baselineCase.id);
    } catch (e: any) {
      message.error(e.message);
    }
  }

  // 渲染录制 Modal 内容
  function renderRecordingContent() {
    if (recordStep === 'config') {
      return (
        <div style={{ padding: '20px 0' }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
              目标 URL
            </label>
            <Input
              placeholder="https://example.com/login"
              value={recordUrl}
              onChange={(e) => setRecordUrl(e.target.value)}
              size="large"
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
              浏览器类型
            </label>
            <Select
              value={recordBrowser}
              onChange={(v) => setRecordBrowser(v)}
              style={{ width: 200 }}
              options={BROWSERS.map((b) => ({ label: b, value: b }))}
            />
          </div>
          <div
            style={{
              background: '#f0f5ff',
              border: '1px solid #adc6ff',
              borderRadius: 6,
              padding: '12px 16px',
              marginBottom: 16,
            }}
          >
            <p style={{ margin: 0, color: '#1d39c4', fontSize: 13 }}>
              <strong>使用说明：</strong>
            </p>
            <ol style={{ margin: '8px 0 0 20px', padding: 0, color: '#1d39c4', fontSize: 13 }}>
              <li>点击「开始录制」后，系统会打开一个浏览器窗口</li>
              <li>在浏览器中正常操作（点击、输入、选择等），系统会自动记录</li>
              <li>操作完成后点击「停止录制」，系统将生成测试步骤</li>
              <li>确认步骤后保存为 UI 测试用例，可随时回放执行</li>
            </ol>
          </div>
          <Button
            type="primary"
            size="large"
            block
            icon={<VideoCameraOutlined />}
            loading={recordLoading}
            onClick={startRecording}
          >
            开始录制
          </Button>
        </div>
      );
    }

    if (recordStep === 'recording') {
      return (
        <div>
          <div
            style={{
              background: '#fff2f0',
              border: '1px solid #ffccc7',
              borderRadius: 6,
              padding: '12px 16px',
              marginBottom: 16,
            }}
          >
            <Space>
              <Spin size="small" />
              <span style={{ color: '#cf1322', fontWeight: 600 }}>
                正在录制中... 请在浏览器窗口中操作
              </span>
            </Space>
          </div>

          {recordError && (
            <div
              style={{
                background: '#fff1f0',
                border: '1px solid #ffa39e',
                borderRadius: 6,
                padding: '8px 12px',
                marginBottom: 16,
                color: '#f5222d',
              }}
            >
              错误: {recordError}
            </div>
          )}

          <Card
            size="small"
            title={`已捕获事件 (${recordEvents.length})`}
            style={{ marginBottom: 16, maxHeight: 350, overflow: 'auto' }}
          >
            {recordEvents.length === 0 ? (
              <Empty description="等待操作中..." />
            ) : (
              <List
                size="small"
                dataSource={recordEvents}
                renderItem={(ev: any, idx: number) => (
                  <List.Item>
                    <Space>
                      <Tag color="blue">{idx + 1}</Tag>
                      <Tag color={
                        ev.action === 'click' ? 'green' :
                        ev.action === 'input' ? 'orange' :
                        ev.action === 'navigate' ? 'purple' :
                        ev.action === 'select' ? 'cyan' :
                        ev.action === 'press' ? 'magenta' :
                        'default'
                      }>
                        {ev.action}
                      </Tag>
                      {ev.selector && (
                        <code style={{ fontSize: 12, color: '#8c8c8c' }}>
                          {ev.selector.substring(0, 50)}
                        </code>
                      )}
                      {ev.value && (
                        <span style={{ fontSize: 12, wordBreak: 'break-all' }}>
                          = “{ev.value.substring(0, 80)}”{ev.value.length > 80 ? '...' : ''}
                        </span>
                      )}
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>

          <Button
            type="primary"
            danger
            size="large"
            block
            icon={<StopOutlined />}
            loading={recordStopping}
            onClick={stopRecording}
          >
            停止录制
          </Button>
        </div>
      );
    }

    // review 步骤
    return (
      <div>
        <div
          style={{
            background: '#f6ffed',
            border: '1px solid #b7eb8f',
            borderRadius: 6,
            padding: '12px 16px',
            marginBottom: 16,
          }}
        >
          <span style={{ color: '#389e0d', fontWeight: 600 }}>
            <CheckCircleOutlined /> 录制完成，共捕获 {recordEvents.length} 个步骤
          </span>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
            用例标题
          </label>
          <Input
            placeholder="请输入用例标题"
            value={saveTitle}
            onChange={(e) => setSaveTitle(e.target.value)}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
            所属项目
          </label>
          <Select
            allowClear
            placeholder="选择项目（可选）"
            value={saveProjectId}
            onChange={(v) => setSaveProjectId(v)}
            style={{ width: '100%' }}
            showSearch
            optionFilterProp="label"
            options={projects.map((p) => ({ label: p.name, value: p.id }))}
          />
        </div>

        <Card
          size="small"
          title="生成的测试步骤"
          style={{ marginBottom: 16, maxHeight: 300, overflow: 'auto' }}
        >
          {recordEvents.length === 0 ? (
            <Empty description="未捕获任何步骤" />
          ) : (
            <Table
              dataSource={recordEvents}
              rowKey={(_, idx) => String(idx)}
              pagination={false}
              size="small"
              columns={[
                {
                  title: '#',
                  width: 50,
                  render: (_, __, idx) => idx + 1,
                },
                {
                  title: '动作',
                  dataIndex: 'action',
                  width: 100,
                  render: (a: string) => (
                    <Tag color={
                      a === 'click' ? 'green' :
                      a === 'input' ? 'orange' :
                      a === 'navigate' ? 'purple' :
                      a === 'select' ? 'cyan' :
                      a === 'press' ? 'magenta' :
                      'default'
                    }>
                      {a}
                    </Tag>
                  ),
                },
                {
                  title: '选择器',
                  dataIndex: 'selector',
                  ellipsis: true,
                  render: (s: string) => s ? <code style={{ fontSize: 12 }}>{s}</code> : '-',
                },
                {
                  title: '值',
                  dataIndex: 'value',
                  ellipsis: true,
                  render: (v: string) => v ? `"${v}"` : '-',
                },
                {
                  title: '描述',
                  dataIndex: 'description',
                  ellipsis: true,
                },
              ]}
            />
          )}
        </Card>

        <Space style={{ width: '100%', justifyContent: 'center' }}>
          <Button onClick={() => { setRecordStep('config'); setSessionId(null); setRecordEvents([]); }}>
            重新录制
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={savingRecording}
            onClick={saveRecording}
            disabled={recordEvents.length === 0}
          >
            保存为用例
          </Button>
        </Space>
      </div>
    );
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <ExperimentOutlined />
            <span>UI 用例管理</span>
            <span style={{ color: '#6b7280', fontSize: 13, fontWeight: 400 }}>
              共 {total} 个用例
            </span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
              刷新
            </Button>
            <Button
              type="primary"
              ghost
              icon={<VideoCameraOutlined />}
              onClick={openRecording}
              data-testid="record-btn"
            >
              录制用例
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-testid="create-ui-case-btn">
              新建 UI 用例
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} size="middle">
          <Select
            allowClear
            placeholder="选择项目"
            style={{ width: 220 }}
            showSearch
            optionFilterProp="label"
            value={filterProject}
            options={projects.map((p) => ({ label: p.name, value: p.id }))}
            onChange={(v) => {
              setFilterProject(v);
              setPage(1);
              loadData(1, pageSize, v, titleSearch);
            }}
          />
          <Input.Search
            placeholder="搜索用例标题"
            allowClear
            style={{ width: 240 }}
            onSearch={(v) => {
              setTitleSearch(v);
              setPage(1);
              loadData(1, pageSize, filterProject, v);
            }}
          />
          <Radio.Group
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="flat">平铺视图</Radio.Button>
            <Radio.Button value="grouped">按项目分组</Radio.Button>
          </Radio.Group>
        </Space>

        {viewMode === 'grouped' ? (
          <Collapse
            defaultActiveKey={Object.keys(groupedData)}
          >
            {Object.entries(groupedData).map(
              ([key, group]) =>
                group.cases.length > 0 && (
                  <Collapse.Panel
                    key={key}
                    header={`${group.projectName} (${group.cases.length})`}
                  >
                    <Table
                      columns={columns}
                      dataSource={group.cases}
                      pagination={false}
                      rowKey="id"
                      size="small"
                    />
                  </Collapse.Panel>
                )
            )}
          </Collapse>
        ) : (
          <Table
            dataSource={data}
            rowKey="id"
            loading={loading}
            data-testid="ui-cases-table"
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
            columns={columns}
            size="middle"
            locale={{ emptyText: <Empty description="暂无 UI 用例" /> }}
          />
        )}
      </Card>

      {/* 新建/编辑 Modal */}
      <Modal
        title={editing ? '编辑 UI 用例' : '新建 UI 用例'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={860}
        destroyOnClose
        data-testid={editing ? 'edit-modal' : 'create-modal'}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ browser_type: 'chrome', is_active: true }}
        >
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item
              name="title"
              label="标题"
              rules={[{ required: true, message: '请输入标题' }]}
              style={{ flex: 1, minWidth: 380 }}
            >
              <Input placeholder="如：登录功能验证" />
            </Form.Item>
            <Form.Item
              name="browser_type"
              label="浏览器类型"
              rules={[{ required: true, message: '请选择浏览器类型' }]}
            >
              <Select
                style={{ width: 160 }}
                options={BROWSERS.map((b) => ({ label: b, value: b }))}
              />
            </Form.Item>
          </Space>

          <Form.Item
            name="url"
            label="起始 URL"
            rules={[{ required: true, message: '请输入起始 URL' }]}
          >
            <Input placeholder="https://example.com/login" />
          </Form.Item>

          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="选择项目（可选）"
              showSearch
              optionFilterProp="label"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input placeholder="用例描述（可选）" />
          </Form.Item>

          {/* 重试配置：失败时自动重试，适合处理 flaky 测试 */}
          <Card size="small" style={{ marginBottom: 16, background: '#fafafa' }}>
            <div style={{ marginBottom: 8, fontWeight: 600, color: '#4f46e5' }}>
              重试配置
            </div>
            <div style={{ marginBottom: 12, color: '#8c8c8c', fontSize: 12 }}>
              用例执行失败时自动重试，适合处理网络波动导致的 flaky 测试
            </div>
            <Space size="large">
              <Form.Item
                name="retry_count"
                label="重试次数"
                tooltip="失败后最多重试的次数（0=不重试）"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={0} max={5} step={1} style={{ width: 120 }} />
              </Form.Item>
              <Form.Item
                name="retry_interval"
                label="重试间隔（秒）"
                tooltip="每次重试前的等待秒数"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={0} max={60} step={0.5} style={{ width: 140 }} />
              </Form.Item>
            </Space>
          </Card>

          <Form.Item label="测试步骤" data-testid="steps-list">
            <Form.List name="steps">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field) => (
                    <div
                      key={field.key}
                      style={{
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        padding: 12,
                        marginBottom: 12,
                        background: '#fafafa',
                      }}
                    >
                      <Space
                        align="baseline"
                        style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}
                        size="small"
                      >
                        <Form.Item
                          {...field}
                          name={[field.name, 'action']}
                          rules={[{ required: true, message: '请选择动作' }]}
                          style={{ marginBottom: 0 }}
                        >
                          <Select
                            style={{ width: 170 }}
                            placeholder="动作类型"
                            options={[
                              ...ACTIONS.map((a) => ({
                                label: ACTION_LABELS[a] || a,
                                value: a,
                              })),
                              // step_group 仅用于展示已插入的步骤组步骤，不允许通过下拉新建
                              { label: ACTION_LABELS['step_group'], value: 'step_group', disabled: true },
                            ]}
                          />
                        </Form.Item>
                        <MinusCircleOutlined
                          style={{ color: '#ff4d4f', fontSize: 16 }}
                          onClick={() => remove(field.name)}
                        />
                      </Space>
                      {/* 根据 action 联动显示不同参数字段 */}
                      <Form.Item
                        noStyle
                        shouldUpdate={(prev, cur) => {
                          const prevAction = prev.steps?.[field.name]?.action;
                          const curAction = cur.steps?.[field.name]?.action;
                          return prevAction !== curAction;
                        }}
                      >
                        {({ getFieldValue }) => {
                          const action = getFieldValue(['steps', field.name, 'action']);
                          return (
                            <Space
                              align="start"
                              style={{ display: 'flex', flexWrap: 'wrap', marginTop: 8, gap: 8 }}
                              size="small"
                            >
                              {/* navigate: value 用作 URL */}
                              {action === 'navigate' && (
                                <Form.Item {...field} name={[field.name, 'value']} style={{ marginBottom: 0 }}>
                                  <Input style={{ width: 320 }} placeholder="目标 URL，如 https://example.com" />
                                </Form.Item>
                              )}
                              {/* 通用 selector + value 组合 */}
                              {['click', 'input', 'assert', 'select', 'press', 'hover'].includes(action) && (
                                <>
                                  <Form.Item {...field} name={[field.name, 'selector']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 220 }} placeholder="选择器，如 #username" />
                                  </Form.Item>
                                  <Form.Item {...field} name={[field.name, 'value']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 180 }} placeholder={action === 'press' ? '键名，如 Enter' : '值，如输入文本/断言值'} />
                                  </Form.Item>
                                </>
                              )}
                              {/* wait: value 用作秒数 */}
                              {action === 'wait' && (
                                <Form.Item {...field} name={[field.name, 'value']} style={{ marginBottom: 0 }}>
                                  <Input style={{ width: 180 }} placeholder="等待秒数，如 2" />
                                </Form.Item>
                              )}
                              {/* screenshot: 无参数 */}
                              {action === 'screenshot' && (
                                <span style={{ color: '#8c8c8c', fontSize: 12, lineHeight: '32px' }}>
                                  截图动作无需额外参数
                                </span>
                              )}
                              {/* drag: source + target */}
                              {action === 'drag' && (
                                <>
                                  <Form.Item {...field} name={[field.name, 'source']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 200 }} placeholder="源元素选择器 source" />
                                  </Form.Item>
                                  <Form.Item {...field} name={[field.name, 'target']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 200 }} placeholder="目标元素选择器 target" />
                                  </Form.Item>
                                </>
                              )}
                              {/* scroll: selector(可选) + direction + amount */}
                              {action === 'scroll' && (
                                <>
                                  <Form.Item {...field} name={[field.name, 'selector']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 200 }} placeholder="元素选择器（可选，留空滚动整页）" />
                                  </Form.Item>
                                  <Form.Item {...field} name={[field.name, 'direction']} style={{ marginBottom: 0 }} initialValue="down">
                                    <Select
                                      style={{ width: 110 }}
                                      options={[
                                        { label: '向下 down', value: 'down' },
                                        { label: '向上 up', value: 'up' },
                                      ]}
                                    />
                                  </Form.Item>
                                  <Form.Item {...field} name={[field.name, 'amount']} style={{ marginBottom: 0 }} initialValue={500}>
                                    <Input style={{ width: 130 }} placeholder="像素数，如 500" />
                                  </Form.Item>
                                </>
                              )}
                              {/* upload: selector + file_path */}
                              {action === 'upload' && (
                                <>
                                  <Form.Item {...field} name={[field.name, 'selector']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 220 }} placeholder="input[type=file] 选择器" />
                                  </Form.Item>
                                  <Form.Item {...field} name={[field.name, 'file_path']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 240 }} placeholder="本地文件路径 file_path" />
                                  </Form.Item>
                                </>
                              )}
                              {/* download: selector + save_path */}
                              {action === 'download' && (
                                <>
                                  <Form.Item {...field} name={[field.name, 'selector']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 220 }} placeholder="下载链接选择器，如 a[download]" />
                                  </Form.Item>
                                  <Form.Item {...field} name={[field.name, 'save_path']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 240 }} placeholder="保存路径 save_path" />
                                  </Form.Item>
                                </>
                              )}
                              {/* step_group: 步骤组引用，展示特殊样式 + 预览按钮 */}
                              {action === 'step_group' && (
                                <>
                                  <Form.Item {...field} name={[field.name, 'step_library_id']} style={{ marginBottom: 0 }}>
                                    <Input style={{ width: 280 }} placeholder="步骤组 ID（通过「插入步骤组」选择）" disabled />
                                  </Form.Item>
                                  <div
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 6,
                                      padding: '4px 10px',
                                      background: '#eef2ff',
                                      border: '1px solid #c7d2fe',
                                      borderRadius: 6,
                                      color: '#4f46e5',
                                      fontSize: 13,
                                    }}
                                  >
                                    <ApartmentOutlined />
                                    <span>步骤组引用</span>
                                  </div>
                                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.steps?.[field.name]?.step_library_id !== cur.steps?.[field.name]?.step_library_id}>
                                    {({ getFieldValue: gfv }) => {
                                      const sgId = gfv(['steps', field.name, 'step_library_id']);
                                      const sgDesc = gfv(['steps', field.name, 'description']);
                                      return (
                                        <Button
                                          size="small"
                                          type="link"
                                          icon={<ApartmentOutlined />}
                                          disabled={!sgId}
                                          onClick={() => previewStepGroup(sgId, sgDesc)}
                                        >
                                          预览子步骤
                                        </Button>
                                      );
                                    }}
                                  </Form.Item>
                                </>
                              )}
                              {/* 描述字段：所有动作通用 */}
                              <Form.Item {...field} name={[field.name, 'description']} style={{ marginBottom: 0 }}>
                                <Input style={{ width: 200 }} placeholder="步骤描述（可选）" />
                              </Form.Item>
                            </Space>
                          );
                        }}
                      </Form.Item>
                    </div>
                  ))}
                  <Button
                    type="dashed"
                    onClick={() => add({ action: 'navigate', direction: 'down', amount: 500 })}
                    icon={<PlusOutlined />}
                    style={{ width: 160 }}
                  >
                    添加步骤
                  </Button>
                  <Button
                    type="dashed"
                    onClick={() => openStepGroupPicker(add)}
                    icon={<ApartmentOutlined />}
                    style={{ width: 160, borderColor: '#4f46e5', color: '#4f46e5' }}
                  >
                    插入步骤组
                  </Button>
                </>
              )}
            </Form.List>
          </Form.Item>
        </Form>
      </Modal>

      {/* 步骤组选择器 Modal（Page Object Model） */}
      <Modal
        title={
          <Space>
            <ApartmentOutlined style={{ color: '#4f46e5' }} />
            <span>插入步骤组</span>
          </Space>
        }
        open={stepGroupPickerOpen}
        onCancel={() => setStepGroupPickerOpen(false)}
        footer={null}
        width={640}
      >
        <Input.Search
          allowClear
          placeholder="搜索步骤组名称/描述"
          style={{ marginBottom: 12 }}
          value={stepGroupSearch}
          onChange={(e) => setStepGroupSearch(e.target.value)}
          onSearch={(v) => searchStepGroups(v)}
          loading={stepGroupLoading}
        />
        {stepGroupLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>加载中...</div>
        ) : stepGroupList.length ? (
          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            {stepGroupList.map((g: any) => (
              <div
                key={g.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 12px',
                  marginBottom: 8,
                  border: '1px solid #e5e7eb',
                  borderRadius: 8,
                  background: '#fafafa',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = '#4f46e5';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = '#e5e7eb';
                }}
                onClick={() => insertStepGroup(g)}
              >
                <Space>
                  <ApartmentOutlined style={{ color: '#4f46e5' }} />
                  <div>
                    <div style={{ fontWeight: 600 }}>{g.name}</div>
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>
                      {g.description || '无描述'} · {g.step_count || 0} 步 · 使用 {g.usage_count || 0} 次
                    </div>
                  </div>
                </Space>
                <Button size="small" type="primary" ghost onClick={(e) => { e.stopPropagation(); insertStepGroup(g); }}>
                  选择
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <Empty description="暂无步骤组，请先在「步骤库」页面创建" />
        )}
      </Modal>

      {/* 步骤组子步骤预览 Modal */}
      <Modal
        title={stepGroupPreview ? `子步骤预览：${stepGroupPreview.name}` : '子步骤预览'}
        open={stepGroupPreviewOpen}
        onCancel={() => setStepGroupPreviewOpen(false)}
        footer={null}
        width={720}
      >
        {stepGroupPreviewLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>加载中...</div>
        ) : stepGroupPreview && stepGroupPreview.steps && stepGroupPreview.steps.length ? (
          <Table
            rowKey={(_r: any, i?: number) => String(i ?? 0)}
            dataSource={stepGroupPreview.steps}
            pagination={false}
            size="small"
            columns={[
              { title: '#', width: 50, render: (_: any, __: any, i: number) => i + 1 },
              {
                title: '动作',
                dataIndex: 'action',
                width: 100,
                render: (a: string) => <Tag color="geekblue">{ACTION_LABELS[a] || a}</Tag>,
              },
              {
                title: '选择器',
                dataIndex: 'selector',
                render: (t: string) => t ? <code style={{ fontSize: 12 }}>{t}</code> : '-',
              },
              { title: '值', dataIndex: 'value', render: (t: string) => t || '-' },
              { title: '描述', dataIndex: 'description', render: (t: string) => t || '-' },
            ]}
          />
        ) : (
          <Empty description="该步骤组暂无子步骤" />
        )}
      </Modal>

      {/* 运行结果 Modal */}
      <Modal
        title="UI 用例运行结果"
        open={resultOpen}
        onCancel={() => {
          setResultOpen(false);
          setRunResult(null);
        }}
        width={900}
        footer={
          <Button
            type="primary"
            onClick={() => {
              setResultOpen(false);
              setRunResult(null);
            }}
          >
            关闭
          </Button>
        }
        destroyOnClose
      >
        {running && !runResult ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin tip="正在执行 UI 自动化测试..." size="large" />
          </div>
        ) : (
          renderResultContent()
        )}
      </Modal>

      {/* 录制用例 Modal */}
      <Modal
        title={
          <Space>
            <VideoCameraOutlined />
            <span>录制 UI 用例</span>
          </Space>
        }
        open={recordOpen}
        onCancel={closeRecording}
        width={700}
        footer={null}
        destroyOnClose
      >
        {renderRecordingContent()}
      </Modal>

      {/* 视觉基线管理 Modal */}
      <Modal
        title={
          <Space>
            <PictureOutlined />
            <span>视觉基线管理 - {baselineCase?.title}</span>
          </Space>
        }
        open={baselineOpen}
        onCancel={() => setBaselineOpen(false)}
        width={760}
        footer={
          <Button type="primary" onClick={() => setBaselineOpen(false)}>
            关闭
          </Button>
        }
        destroyOnClose
      >
        {/* 已有基线列表 */}
        <Card
          size="small"
          title={`已有基线 (${baselines.length})`}
          style={{ marginBottom: 16 }}
        >
          <Table
            dataSource={baselines}
            rowKey="id"
            loading={baselineLoading}
            pagination={false}
            size="small"
            locale={{ emptyText: <Empty description="暂无基线，下方新建" /> }}
            columns={[
              { title: '名称', dataIndex: 'name', ellipsis: true },
              {
                title: '阈值',
                dataIndex: 'threshold',
                width: 80,
                render: (v: number) => (v ?? 0.1).toFixed(2),
              },
              {
                title: '基线截图',
                dataIndex: 'baseline_image',
                width: 100,
                render: (img: string) =>
                  img ? (
                    <Image
                      src={`data:image/png;base64,${img}`}
                      alt="基线"
                      width={80}
                      style={{ borderRadius: 4, border: '1px solid #d9d9d9' }}
                    />
                  ) : (
                    '-'
                  ),
              },
              {
                title: '创建时间',
                dataIndex: 'created_at',
                width: 140,
                render: (t: string) =>
                  t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-',
              },
              {
                title: '操作',
                width: 80,
                render: (_: any, r: any) => (
                  <Popconfirm
                    title="确认删除该基线？"
                    onConfirm={() => deleteBaseline(r.id)}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                ),
              },
            ]}
          />
        </Card>

        {/* 新建基线 */}
        <Card size="small" title="新建基线">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
                基线名称
              </label>
              <Input
                value={newBaselineName}
                onChange={(e) => setNewBaselineName(e.target.value)}
                placeholder="如：登录页-基线"
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
                差异阈值（0-1，差异分数小于等于阈值视为通过）
              </label>
              <Input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={newBaselineThreshold}
                onChange={(e) => setNewBaselineThreshold(Number(e.target.value))}
                style={{ width: 200 }}
              />
            </div>
            <Space>
              <Upload
                accept="image/*"
                showUploadList={false}
                beforeUpload={handleUploadImage}
              >
                <Button icon={<UploadOutlined />}>上传基线图片</Button>
              </Upload>
              <Button
                icon={<CameraOutlined />}
                onClick={setBaselineFromLatestRun}
              >
                从最新执行截图设为基线
              </Button>
            </Space>
            {newBaselineImage && (
              <div>
                <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 6 }}>
                  基线图片预览：
                </div>
                <Image
                  src={
                    newBaselineImage.startsWith('data:')
                      ? newBaselineImage
                      : `data:image/png;base64,${newBaselineImage}`
                  }
                  alt="基线预览"
                  width={360}
                  style={{ borderRadius: 6, border: '1px solid #d9d9d9' }}
                />
              </div>
            )}
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={savingBaseline}
              onClick={saveBaseline}
              disabled={!newBaselineImage}
            >
              保存基线
            </Button>
          </Space>
        </Card>
      </Modal>
    </div>
  );
}
