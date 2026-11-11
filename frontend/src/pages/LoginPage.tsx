import { useState } from 'react';
import { Card, Form, Input, Button, message, ConfigProvider, Divider } from 'antd';
import {
  ExperimentOutlined,
  LockOutlined,
  MailOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth, authApi } from '../contexts/AuthContext';
import '../styles/login.css';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'login' | 'register'>('login');

  async function handleLogin(values: { username: string; password: string }) {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success('登录成功');
      navigate('/dashboard', { replace: true });
    } catch (e: any) {
      message.error(e.message || '登录失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(values: {
    username: string;
    email: string;
    password: string;
  }) {
    setLoading(true);
    try {
      await authApi.register({
        username: values.username,
        email: values.email,
        password: values.password,
        is_active: true,
      });
      message.success('注册成功，首个账号已自动成为管理员，请登录');
      setMode('login');
    } catch (e: any) {
      message.error(e.message || '注册失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#2563eb',
          borderRadius: 8,
        },
      }}
    >
      <div className="login-page">
        <Card className="login-card">
          <div className="login-heading">
            <div className="login-mark" aria-hidden="true">
              <ExperimentOutlined />
            </div>
            <h1 className="login-title">AI 测试平台</h1>
            <p className="login-subtitle">
              {mode === 'login' ? '登录以继续' : '创建首个管理员账号'}
            </p>
          </div>

          {mode === 'login' ? (
            <Form layout="vertical" onFinish={handleLogin} size="large">
              <Form.Item
                name="username"
                label="用户名"
                rules={[{ required: true, message: '请输入用户名' }]}
              >
                <Input prefix={<UserOutlined />} placeholder="用户名" data-testid="username-input" />
              </Form.Item>
              <Form.Item
                name="password"
                label="密码"
                rules={[{ required: true, message: '请输入密码' }]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="密码" data-testid="password-input" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  loading={loading}
                  data-testid="login-submit"
                >
                  登录
                </Button>
              </Form.Item>
            </Form>
          ) : (
            <Form layout="vertical" onFinish={handleRegister} size="large">
              <Form.Item
                name="username"
                label="用户名"
                rules={[
                  { required: true, message: '请输入用户名' },
                  { min: 3, message: '用户名至少 3 个字符' },
                ]}
              >
                <Input prefix={<UserOutlined />} placeholder="用户名" />
              </Form.Item>
              <Form.Item
                name="email"
                label="邮箱"
                rules={[
                  { required: true, message: '请输入邮箱' },
                  { type: 'email', message: '邮箱格式不正确' },
                ]}
              >
                <Input prefix={<MailOutlined />} placeholder="邮箱" />
              </Form.Item>
              <Form.Item
                name="password"
                label="密码"
                rules={[
                  { required: true, message: '请输入密码' },
                  { min: 6, message: '密码至少 6 个字符' },
                ]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="密码" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  loading={loading}
                >
                  注册
                </Button>
              </Form.Item>
            </Form>
          )}

          <Divider style={{ margin: '20px 0 12px' }} />
          <div style={{ textAlign: 'center', fontSize: 13 }}>
            {mode === 'login' ? (
              <span style={{ color: '#6b7280' }}>
                还没有账号？
                <Button
                  type="link"
                  size="small"
                  style={{ padding: '0 4px' }}
                  onClick={() => setMode('register')}
                  data-testid="register-link"
                >
                  注册首个管理员
                </Button>
              </span>
            ) : (
              <span style={{ color: '#6b7280' }}>
                已有账号？
                <Button
                  type="link"
                  size="small"
                  style={{ padding: '0 4px' }}
                  onClick={() => setMode('login')}
                >
                  返回登录
                </Button>
              </span>
            )}
          </div>
        </Card>
      </div>
    </ConfigProvider>
  );
}
