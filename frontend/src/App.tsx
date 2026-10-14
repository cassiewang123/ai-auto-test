import { Suspense } from 'react';
import { useRoutes } from 'react-router-dom';
import { Spin } from 'antd';
import { PageTabsProvider } from './contexts/PageTabsContext';
import { routeObjects } from './routes';

function RouteFallback() {
  return (
    <div
      style={{
        minHeight: 320,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Spin size="large" />
    </div>
  );
}

export default function App() {
  const element = useRoutes(routeObjects);

  return (
    <Suspense fallback={<RouteFallback />}>
      <PageTabsProvider>{element}</PageTabsProvider>
    </Suspense>
  );
}
