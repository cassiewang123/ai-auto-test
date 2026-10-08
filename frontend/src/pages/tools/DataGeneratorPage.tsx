import { useState } from 'react';
import {
  Button,
  Card,
  InputNumber,
  Select,
  Space,
  Table,
  message,
} from 'antd';
import {
  CopyOutlined,
  DownloadOutlined,
  FileTextOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import {
  generateData,
  type DataKind,
} from '../../utils/tools/randomData';

const dataOptions: Array<{ value: DataKind; label: string }> = [
  { value: 'name', label: '姓名' },
  { value: 'email', label: '邮箱' },
  { value: 'phone', label: '手机号' },
  { value: 'idCard', label: '身份证号' },
  { value: 'ip', label: 'IP 地址' },
  { value: 'address', label: '地址' },
  { value: 'company', label: '公司名称' },
  { value: 'uuid', label: 'UUID' },
  { value: 'bankCard', label: '银行卡号' },
  { value: 'date', label: '日期' },
];

export default function DataGeneratorPage() {
  const [kind, setKind] = useState<DataKind>('name');
  const [count, setCount] = useState(10);
  const [rows, setRows] = useState<string[]>([]);

  function handleGenerate() {
    setRows(generateData(kind, count));
  }

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(rows.join('\n'));
      message.success('数据已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  function downloadAll() {
    const blob = new Blob([rows.join('\n')], { type: 'text/plain;charset=utf-8' });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `${kind}-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <ToolPage
      icon={<FileTextOutlined />}
      title="测试数据生成"
      description="批量生成常用测试数据，仅用于本地调试和造数。"
      extra={
        <Space wrap>
          <Button
            icon={<CopyOutlined />}
            onClick={copyAll}
            disabled={rows.length === 0}
          >
            复制全部
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={downloadAll}
            disabled={rows.length === 0}
          >
            导出
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card size="small" title="生成设置">
          <Space wrap size="middle">
            <Select
              style={{ width: 180 }}
              value={kind}
              options={dataOptions}
              onChange={(value) => setKind(value)}
              data-testid="data-kind"
            />
            <InputNumber
              min={1}
              max={1000}
              value={count}
              addonBefore="数量"
              onChange={(value) => setCount(value ?? 1)}
            />
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={handleGenerate}
              data-testid="data-generate"
            >
              生成数据
            </Button>
          </Space>
        </Card>

        <Card size="small" title={`生成结果（${rows.length} 条）`}>
          <Table
            rowKey={(_record, index) => String(index)}
            dataSource={rows.map((value, index) => ({ index: index + 1, value }))}
            size="small"
            pagination={{ pageSize: 20, showSizeChanger: false }}
            columns={[
              { title: '#', dataIndex: 'index', width: 80 },
              {
                title: '生成值',
                dataIndex: 'value',
                render: (value: string) => <code>{value}</code>,
              },
              {
                title: '操作',
                width: 100,
                render: (_value, record) => (
                  <Button
                    type="link"
                    size="small"
                    onClick={async () => {
                      await navigator.clipboard.writeText(record.value);
                      message.success('已复制');
                    }}
                  >
                    复制
                  </Button>
                ),
              },
            ]}
            locale={{ emptyText: '选择类型和数量后点击“生成数据”' }}
          />
        </Card>
      </div>
    </ToolPage>
  );
}
