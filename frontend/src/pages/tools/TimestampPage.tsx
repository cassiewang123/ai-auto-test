import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  Row,
  Space,
  Tabs,
  message,
} from 'antd';
import {
  ClockCircleOutlined,
  CopyOutlined,
  FieldTimeOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import {
  dateToTimestamp,
  formatLocalDate,
  timestampToDate,
} from '../../utils/tools/timestampTool';

export default function TimestampPage() {
  const [now, setNow] = useState(() => new Date());
  const [dateInput, setDateInput] = useState(() => formatLocalDate(new Date()));
  const [timestampInput, setTimestampInput] = useState(() =>
    String(Math.floor(Date.now() / 1000))
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const dateResult = useMemo(() => dateToTimestamp(dateInput), [dateInput]);
  const timestampResult = useMemo(
    () => timestampToDate(timestampInput),
    [timestampInput]
  );

  async function copy(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      message.success(`${label}已复制`);
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  const currentDescriptions = (
    <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} size="small">
      <Descriptions.Item label="本地时间">{formatLocalDate(now)}</Descriptions.Item>
      <Descriptions.Item label="ISO 时间">{now.toISOString()}</Descriptions.Item>
      <Descriptions.Item label="秒级时间戳">
        <Space>
          <span data-testid="current-seconds">{Math.floor(now.getTime() / 1000)}</span>
          <Button
            type="link"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copy(String(Math.floor(now.getTime() / 1000)), '秒级时间戳')}
          />
        </Space>
      </Descriptions.Item>
      <Descriptions.Item label="毫秒级时间戳">
        <Space>
          <span>{now.getTime()}</span>
          <Button
            type="link"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copy(String(now.getTime()), '毫秒级时间戳')}
          />
        </Space>
      </Descriptions.Item>
    </Descriptions>
  );

  return (
    <ToolPage
      icon={<FieldTimeOutlined />}
      title="时间处理"
      description="日期与秒级、毫秒级时间戳互转，同时查看当前时间。"
      extra={
        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            const current = new Date();
            setNow(current);
            setDateInput(formatLocalDate(current));
            setTimestampInput(String(Math.floor(current.getTime() / 1000)));
          }}
        >
          使用当前时间
        </Button>
      }
    >
      <div className="tools-page-body">
        <Card
          size="small"
          title={
            <Space>
              <ClockCircleOutlined />
              <span>当前时间</span>
            </Space>
          }
        >
          {currentDescriptions}
        </Card>

        <Tabs
          items={[
            {
              key: 'date-to-timestamp',
              label: '日期转时间戳',
              children: (
                <Card size="small">
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Input
                      value={dateInput}
                      onChange={(event) => setDateInput(event.target.value)}
                      placeholder="2026-10-08 13:47:59 或 2026-10-08T13:47:59+08:00"
                      data-testid="date-input"
                    />
                    {!dateResult.valid ? (
                      <Alert type="error" showIcon title={dateResult.error} />
                    ) : (
                      <Row gutter={[16, 16]}>
                        <Col xs={24} md={8}>
                          <Card size="small" title="秒级时间戳">
                            <Space>
                              <code data-testid="converted-seconds">{dateResult.seconds}</code>
                              <Button
                                type="link"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => copy(String(dateResult.seconds), '秒级时间戳')}
                              />
                            </Space>
                          </Card>
                        </Col>
                        <Col xs={24} md={8}>
                          <Card size="small" title="毫秒级时间戳">
                            {dateResult.milliseconds}
                          </Card>
                        </Col>
                        <Col xs={24} md={8}>
                          <Card size="small" title="ISO 时间">
                            {dateResult.iso}
                          </Card>
                        </Col>
                      </Row>
                    )}
                  </Space>
                </Card>
              ),
            },
            {
              key: 'timestamp-to-date',
              label: '时间戳转日期',
              children: (
                <Card size="small">
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Input
                      value={timestampInput}
                      onChange={(event) => setTimestampInput(event.target.value)}
                      placeholder="输入 10 位秒级或 13 位毫秒级时间戳"
                      data-testid="timestamp-input"
                    />
                    {!timestampResult.valid ? (
                      <Alert type="error" showIcon title={timestampResult.error} />
                    ) : (
                      <Row gutter={[16, 16]}>
                        <Col xs={24} md={12}>
                          <Card size="small" title="本地时间">
                            <Space>
                              <span data-testid="converted-local">
                                {timestampResult.local}
                              </span>
                              <Button
                                type="link"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => copy(timestampResult.local, '本地时间')}
                              />
                            </Space>
                          </Card>
                        </Col>
                        <Col xs={24} md={12}>
                          <Card size="small" title="ISO 时间">
                            {timestampResult.iso}
                          </Card>
                        </Col>
                      </Row>
                    )}
                  </Space>
                </Card>
              ),
            },
          ]}
        />
      </div>
    </ToolPage>
  );
}
