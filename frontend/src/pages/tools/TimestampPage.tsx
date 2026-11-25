import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  Row,
  Select,
  Space,
  Tabs,
} from 'antd';
import {
  ClockCircleOutlined,
  CopyOutlined,
  FieldTimeOutlined,
  GlobalOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import ToolPage from '../../components/ToolPage';
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard';
import { usePersistentState } from '../../hooks/usePersistentState';
import {
  dateToTimestamp,
  formatLocalDate,
  timestampToDate,
} from '../../utils/tools/timestampTool';

/** 'local' 表示浏览器本地时区（不传 timeZone，保持历史默认行为）。 */
const LOCAL_TIMEZONE = 'local';

const timezoneOptions = [
  { value: LOCAL_TIMEZONE, label: '本地时区（浏览器）' },
  { value: 'UTC', label: 'UTC' },
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai（东八区）' },
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo（东九区）' },
  { value: 'Europe/London', label: 'Europe/London' },
  { value: 'America/New_York', label: 'America/New_York' },
];

const TIMEZONE_STORAGE_KEY = 'airetest.tools.timestamp.timezone';

export default function TimestampPage() {
  const [now, setNow] = useState(() => new Date());
  const [dateInput, setDateInput] = useState(() => formatLocalDate(new Date()));
  const [timestampInput, setTimestampInput] = useState(() =>
    String(Math.floor(Date.now() / 1000))
  );
  const [timezone, setTimezone] = usePersistentState<string>(
    TIMEZONE_STORAGE_KEY,
    LOCAL_TIMEZONE
  );
  const { copy } = useCopyToClipboard();

  // 选中的 IANA 时区；'local' 时为 undefined，全部函数走默认本地行为
  const timeZone = timezone === LOCAL_TIMEZONE ? undefined : timezone;
  const timezoneLabel =
    timezoneOptions.find((option) => option.value === timezone)?.label ?? timezone;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const dateResult = useMemo(
    () => dateToTimestamp(dateInput, timeZone),
    [dateInput, timeZone]
  );
  const timestampResult = useMemo(
    () => timestampToDate(timestampInput, timeZone),
    [timestampInput, timeZone]
  );

  function copyValue(value: string, label: string) {
    void copy(value, {
      successMessage: `${label}已复制`,
      errorMessage: '复制失败，请检查浏览器剪贴板权限',
    });
  }

  const currentDescriptions = (
    <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} size="small">
      <Descriptions.Item label={timezone === LOCAL_TIMEZONE ? '本地时间' : `${timezoneLabel} 时间`}>
        {formatLocalDate(now, timeZone)}
      </Descriptions.Item>
      <Descriptions.Item label="ISO 时间（UTC）">{now.toISOString()}</Descriptions.Item>
      <Descriptions.Item label="秒级时间戳">
        <Space>
          <span data-testid="current-seconds">{Math.floor(now.getTime() / 1000)}</span>
          <Button
            type="link"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copyValue(String(Math.floor(now.getTime() / 1000)), '秒级时间戳')}
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
            onClick={() => copyValue(String(now.getTime()), '毫秒级时间戳')}
          />
        </Space>
      </Descriptions.Item>
    </Descriptions>
  );

  return (
    <ToolPage
      icon={<FieldTimeOutlined />}
      title="时间处理"
      description="日期与秒级、毫秒级时间戳互转，同时查看当前时间，支持按指定时区解析与展示。"
      extra={
        <Space wrap>
          <Select
            style={{ width: 230 }}
            value={timezone}
            options={timezoneOptions}
            onChange={(value) => setTimezone(value)}
            suffixIcon={<GlobalOutlined />}
            data-testid="timestamp-timezone"
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              const current = new Date();
              setNow(current);
              // 按当前选中时区生成可回读的日期串，保证「使用当前时间」在任意时区下都能往返
              setDateInput(formatLocalDate(current, timeZone));
              setTimestampInput(String(Math.floor(current.getTime() / 1000)));
            }}
          >
            使用当前时间
          </Button>
        </Space>
      }
    >
      <div className="tools-page-body">
        <Card
          size="small"
          title={
            <Space>
              <ClockCircleOutlined />
              <span>当前时间</span>
              <span className="tools-timezone-hint">{timezoneLabel}</span>
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
                    <Alert
                      type="info"
                      showIcon
                      title={`不带时区的输入按「${timezoneLabel}」解析；带 Z / ±hh:mm 的 ISO 字符串按其自带偏移解析。`}
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
                                onClick={() => copyValue(String(dateResult.seconds), '秒级时间戳')}
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
                          <Card size="small" title={timezone === LOCAL_TIMEZONE ? '本地时间' : `${timezoneLabel} 时间`}>
                            <Space>
                              <span data-testid="converted-local">
                                {timestampResult.local}
                              </span>
                              <Button
                                type="link"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => copyValue(timestampResult.local, '时间字符串')}
                              />
                            </Space>
                          </Card>
                        </Col>
                        <Col xs={24} md={12}>
                          <Card size="small" title="ISO 时间（UTC）">
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
