import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  ClearOutlined,
  CopyOutlined,
  DownloadOutlined,
  DiffOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import JsonEditor from '../components/JsonEditor';
import {
  compareJson,
  jsonDiffLabel,
  type JsonDifference,
} from '../utils/jsonCompare';
import { formatJson, validateJsonText } from '../utils/json';

const diffColor: Record<JsonDifference['kind'], string> = {
  added: 'green',
  removed: 'red',
  changed: 'orange',
  type_changed: 'purple',
};

function printValue(value: unknown): string {
  if (value === undefined) return '-';
  return typeof value === 'string' ? JSON.stringify(value) : formatJson(value);
}

export default function JsonComparePage() {
  const [leftText, setLeftText] = useState('');
  const [rightText, setRightText] = useState('');
  const [ignoreArrayOrder, setIgnoreArrayOrder] = useState(false);
  const [differences, setDifferences] = useState<JsonDifference[] | null>(null);

  const leftValidation = useMemo(
    () => validateJsonText(leftText, { allowEmpty: false }),
    [leftText]
  );
  const rightValidation = useMemo(
    () => validateJsonText(rightText, { allowEmpty: false }),
    [rightText]
  );

  const summary = useMemo(() => {
    const result = { added: 0, removed: 0, changed: 0, typeChanged: 0 };
    differences?.forEach((item) => {
      if (item.kind === 'added') result.added += 1;
      else if (item.kind === 'removed') result.removed += 1;
      else if (item.kind === 'changed') result.changed += 1;
      else result.typeChanged += 1;
    });
    return result;
  }, [differences]);

  function handleCompare() {
    if (!leftValidation.valid) {
      message.error(`左侧 JSON 无效：${leftValidation.error}`);
      return;
    }
    if (!rightValidation.valid) {
      message.error(`右侧 JSON 无效：${rightValidation.error}`);
      return;
    }
    setDifferences(
      compareJson(leftValidation.value, rightValidation.value, {
        ignoreArrayOrder,
      })
    );
  }

  function buildReport(): string | null {
    if (differences === null) {
      message.warning('请先执行对比');
      return null;
    }
    const lines = [
      'JSON 对比报告',
      `数组顺序：${ignoreArrayOrder ? '忽略' : '参与比较'}`,
      `差异总数：${differences.length}`,
      `新增：${summary.added}，删除：${summary.removed}，修改：${summary.changed}，类型变化：${summary.typeChanged}`,
      '',
      ...differences.map(
        (item) =>
          `[${jsonDiffLabel(item.kind)}] ${item.path}\n  左侧: ${printValue(item.left)}\n  右侧: ${printValue(item.right)}`
      ),
    ];
    return lines.join('\n');
  }

  async function copyReport() {
    const report = buildReport();
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report);
      message.success('对比报告已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadReport() {
    const report = buildReport();
    if (!report) return;
    const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `json-compare-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    message.success('对比报告已导出');
  }

  function clearAll() {
    setLeftText('');
    setRightText('');
    setDifferences(null);
  }

  function swapInputs() {
    setLeftText(rightText);
    setRightText(leftText);
    setDifferences(null);
  }

  const columns = [
    {
      title: '类型',
      dataIndex: 'kind',
      width: 100,
      render: (kind: JsonDifference['kind']) => (
        <Tag color={diffColor[kind]}>{jsonDiffLabel(kind)}</Tag>
      ),
    },
    {
      title: '路径',
      dataIndex: 'path',
      width: 260,
      render: (path: string) => <code>{path}</code>,
    },
    {
      title: '左侧 JSON',
      dataIndex: 'left',
      render: (value: unknown) => (
        <Tooltip title={<pre style={{ margin: 0 }}>{printValue(value)}</pre>}>
          <code>{printValue(value)}</code>
        </Tooltip>
      ),
    },
    {
      title: '右侧 JSON',
      dataIndex: 'right',
      render: (value: unknown) => (
        <Tooltip title={<pre style={{ margin: 0 }}>{printValue(value)}</pre>}>
          <code>{printValue(value)}</code>
        </Tooltip>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <DiffOutlined />
            <span>JSON 对比</span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<SwapOutlined />} onClick={swapInputs}>
              交换
            </Button>
            <Button icon={<ClearOutlined />} onClick={clearAll}>
              清空
            </Button>
            <Button type="primary" icon={<DiffOutlined />} onClick={handleCompare}>
              开始对比
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="所有 JSON 对比都在当前浏览器内完成，不会上传到外部网站。"
          description="支持对象、数组和基本类型；对象字段顺序不会影响结果，可选择是否忽略数组顺序。"
        />
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card size="small" title="左侧 JSON">
              <JsonEditor
                value={leftText}
                onChange={(value) => {
                  setLeftText(value);
                  setDifferences(null);
                }}
                allowEmpty={false}
                rows={18}
                placeholder='{"id": 1}'
                data-testid="json-compare-left"
              />
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card size="small" title="右侧 JSON">
              <JsonEditor
                value={rightText}
                onChange={(value) => {
                  setRightText(value);
                  setDifferences(null);
                }}
                allowEmpty={false}
                rows={18}
                placeholder='{"id": 2}'
                data-testid="json-compare-right"
              />
            </Card>
          </Col>
        </Row>
        <Space style={{ marginTop: 16 }} wrap>
          <Checkbox
            checked={ignoreArrayOrder}
            onChange={(event) => {
              setIgnoreArrayOrder(event.target.checked);
              setDifferences(null);
            }}
          >
            忽略数组顺序
          </Checkbox>
          <span style={{ color: '#6b7280' }}>
            对象字段顺序始终忽略
          </span>
        </Space>
      </Card>

      <Card
        title="对比结果"
        style={{ marginTop: 16 }}
        extra={
          <Space>
            <Button
              icon={<CopyOutlined />}
              onClick={copyReport}
              disabled={differences === null}
            >
              复制报告
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={downloadReport}
              disabled={differences === null}
            >
              导出报告
            </Button>
          </Space>
        }
      >
        {differences === null ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="输入两份有效 JSON 后点击“开始对比”"
          />
        ) : differences.length === 0 ? (
          <Alert
            type="success"
            showIcon
            title="两份 JSON 一致"
            description="在当前比较选项下未发现结构、类型或值差异。"
          />
        ) : (
          <>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={12} sm={6}>
                <Statistic title="差异总数" value={differences.length} />
              </Col>
              <Col xs={12} sm={6}>
                <Statistic title="新增" value={summary.added} styles={{ content: { color: '#059669' } }} />
              </Col>
              <Col xs={12} sm={6}>
                <Statistic title="删除" value={summary.removed} styles={{ content: { color: '#dc2626' } }} />
              </Col>
              <Col xs={12} sm={6}>
                <Statistic
                  title="修改/类型变化"
                  value={summary.changed + summary.typeChanged}
                  styles={{ content: { color: '#d97706' } }}
                />
              </Col>
            </Row>
            <Table
              dataSource={differences}
              rowKey={(record) => `${record.kind}-${record.path}`}
              columns={columns}
              size="small"
              pagination={{ pageSize: 20, showSizeChanger: true }}
              scroll={{ x: 900 }}
            />
          </>
        )}
      </Card>
    </div>
  );
}
