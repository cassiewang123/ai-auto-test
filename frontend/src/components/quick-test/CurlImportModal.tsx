/**
 * 导入 cURL 弹窗：粘贴命令 → 解析 → 回填表单。
 *
 * 解析失败时展示可读错误，且不清空已输入文本，方便用户修正。
 */
import { useEffect, useState } from 'react';
import { Alert, Input, Modal, Space, Tag } from 'antd';
import { parseCurl, type ParsedCurl } from '../../utils/tools/curl';

const SAMPLE = `curl -X POST 'https://api.example.com/users' \\
  -H 'Content-Type: application/json' \\
  -d '{"name": "Ada"}'`;

export interface CurlImportModalProps {
  open: boolean;
  onCancel: () => void;
  /** 解析成功后的回填回调 */
  onImport: (parsed: ParsedCurl) => void;
}

export default function CurlImportModal({
  open,
  onCancel,
  onImport,
}: CurlImportModalProps) {
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
    }
  }, [open]);

  function handleImport() {
    if (!text.trim()) {
      setError('请粘贴 cURL 命令');
      return;
    }
    try {
      const parsed = parseCurl(text);
      setError(null);
      onImport(parsed);
      setText('');
    } catch (parseError: any) {
      setError(parseError?.message || 'cURL 解析失败');
    }
  }

  return (
    <Modal
      title="导入 cURL"
      open={open}
      onCancel={() => {
        setError(null);
        onCancel();
      }}
      onOk={handleImport}
      okText="解析并回填"
      cancelText="取消"
      width={620}
      destroyOnHidden
      data-testid="curl-import-modal"
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <div style={{ color: '#64748b', fontSize: 13 }}>
          支持 <Tag variant="filled">-X/--request</Tag>
          <Tag variant="filled">-H/--header</Tag>
          <Tag variant="filled">-d/--data-raw</Tag>
          <Tag variant="filled">--url</Tag>
          ，以及把 URL 直接写在参数里；<code>-k/-L/-s/-v</code> 等选项会被忽略。
        </div>
        <Input.TextArea
          rows={10}
          value={text}
          placeholder={SAMPLE}
          onChange={(event) => setText(event.target.value)}
          style={{ fontFamily: 'Consolas, "Courier New", monospace', fontSize: 13 }}
          data-testid="curl-import-input"
          autoFocus
        />
        {error && (
          <Alert
            type="error"
            showIcon
            title="解析失败"
            description={error}
            data-testid="curl-import-error"
          />
        )}
      </Space>
    </Modal>
  );
}
