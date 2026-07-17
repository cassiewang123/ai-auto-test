import {
  Component,
  type ErrorInfo,
  type ReactNode,
} from 'react';
import { Button, Result, Space } from 'antd';
import { HomeOutlined, ReloadOutlined } from '@ant-design/icons';

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  error: Error | null;
}

export default class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled application error', error, info.componentStack);
  }

  private handleRetry = () => {
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <Result
        status="error"
        title="页面加载失败"
        subTitle="当前页面发生异常。你可以重试，或返回仪表盘继续使用。"
        data-testid="app-error-boundary"
        extra={
          <Space>
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={this.handleRetry}
            >
              重试
            </Button>
            <Button
              icon={<HomeOutlined />}
              onClick={() => window.location.assign('/dashboard')}
            >
              返回仪表盘
            </Button>
          </Space>
        }
      />
    );
  }
}
