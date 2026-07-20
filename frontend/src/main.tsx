import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import AppErrorBoundary from './components/AppErrorBoundary';
import { AuthProvider } from './contexts/AuthContext';
import { WorkspaceProvider } from './contexts/WorkspaceContext';
import 'antd/dist/reset.css';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppErrorBoundary>
        <AuthProvider>
          <WorkspaceProvider>
            <App />
          </WorkspaceProvider>
        </AuthProvider>
      </AppErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>
);
