import { lazy } from 'react';
import { Navigate, type RouteObject } from 'react-router-dom';
import AppLayout from './components/AppLayout';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const QuickTestPage = lazy(() => import('./pages/QuickTestPage'));
const ApiListPage = lazy(() => import('./pages/ApiListPage'));
const ImportPage = lazy(() => import('./pages/ImportPage'));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const EnvironmentsPage = lazy(() => import('./pages/EnvironmentsPage'));
const GlobalVariablesPage = lazy(() => import('./pages/GlobalVariablesPage'));
const TestCasesPage = lazy(() => import('./pages/TestCasesPage'));
const TestPlansPage = lazy(() => import('./pages/TestPlansPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const CoveragePage = lazy(() => import('./pages/CoveragePage'));
const ApiDocsPage = lazy(() => import('./pages/ApiDocsPage'));
const ScheduledTasksPage = lazy(() => import('./pages/ScheduledTasksPage'));
const MockServicePage = lazy(() => import('./pages/MockServicePage'));
const HistoryPage = lazy(() => import('./pages/HistoryPage'));
const AIPage = lazy(() => import('./pages/AIPage'));
const UiTestCasesPage = lazy(() => import('./pages/UiTestCasesPage'));
const UiTestSuitesPage = lazy(() => import('./pages/UiTestSuitesPage'));
const StepLibraryPage = lazy(() => import('./pages/StepLibraryPage'));
const UiElementsPage = lazy(() => import('./pages/UiElementsPage'));
const UiTestRecordsPage = lazy(() => import('./pages/UiTestRecordsPage'));
const UiTestLogsPage = lazy(() => import('./pages/UiTestLogsPage'));
const PerformanceTestPage = lazy(() => import('./pages/PerformanceTestPage'));
const PerformanceReportPage = lazy(() => import('./pages/PerformanceReportPage'));
const PerfDashboardPage = lazy(() => import('./pages/PerfDashboardPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const UsersPage = lazy(() => import('./pages/UsersPage'));
const RolesPage = lazy(() => import('./pages/RolesPage'));
const ApiTokensPage = lazy(() => import('./pages/ApiTokensPage'));
const CiCdPage = lazy(() => import('./pages/CiCdPage'));
const TestDataPage = lazy(() => import('./pages/TestDataPage'));
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'));
const DefectPatternsPage = lazy(() => import('./pages/DefectPatternsPage'));
const BusinessRulesPage = lazy(() => import('./pages/BusinessRulesPage'));
const InterfaceKnowledgePage = lazy(() => import('./pages/InterfaceKnowledgePage'));
const JobsPage = lazy(() => import('./pages/JobsPage'));
const AuditLogsPage = lazy(() => import('./pages/AuditLogsPage'));
const AiOpsPage = lazy(() => import('./pages/AiOpsPage'));
const QualityGatesPage = lazy(() => import('./pages/QualityGatesPage'));
const DefectsPage = lazy(() => import('./pages/DefectsPage'));
const ToolsHubPage = lazy(() => import('./pages/tools/ToolsHubPage'));
const JsonComparePage = lazy(() => import('./pages/tools/JsonComparePage'));
const JsonFormatterPage = lazy(() => import('./pages/tools/JsonFormatterPage'));
const SqlFormatterPage = lazy(() => import('./pages/tools/SqlFormatterPage'));
const TextComparePage = lazy(() => import('./pages/tools/TextComparePage'));
const RegexTesterPage = lazy(() => import('./pages/tools/RegexTesterPage'));
const EncodingPage = lazy(() => import('./pages/tools/EncodingPage'));
const WordCountPage = lazy(() => import('./pages/tools/WordCountPage'));
const TimestampPage = lazy(() => import('./pages/tools/TimestampPage'));
const DataGeneratorPage = lazy(() => import('./pages/tools/DataGeneratorPage'));
const LogAnalysisPage = lazy(() => import('./pages/tools/LogAnalysisPage'));

/**
 * 路由表单独导出，供 <Routes> 与标签页保活容器共用：
 * 保活容器需要用 matchRoutes 找到当前页面元素并缓存起来。
 */
export const routeObjects: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    element: <AppLayout />,
    children: [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/jobs', element: <JobsPage /> },
      { path: '/quick-test', element: <QuickTestPage /> },
      { path: '/tools', element: <ToolsHubPage /> },
      { path: '/tools/json-compare', element: <JsonComparePage /> },
      { path: '/tools/json-format', element: <JsonFormatterPage /> },
      { path: '/tools/sql-format', element: <SqlFormatterPage /> },
      { path: '/tools/text-compare', element: <TextComparePage /> },
      { path: '/tools/regex', element: <RegexTesterPage /> },
      { path: '/tools/encoding', element: <EncodingPage /> },
      { path: '/tools/word-count', element: <WordCountPage /> },
      { path: '/tools/timestamp', element: <TimestampPage /> },
      { path: '/tools/data-generator', element: <DataGeneratorPage /> },
      { path: '/tools/log-analysis', element: <LogAnalysisPage /> },
      { path: '/json-compare', element: <Navigate to="/tools/json-compare" replace /> },
      { path: '/api-list', element: <ApiListPage /> },
      { path: '/projects', element: <ProjectsPage /> },
      { path: '/import', element: <ImportPage /> },
      { path: '/environments', element: <EnvironmentsPage /> },
      { path: '/variables', element: <GlobalVariablesPage /> },
      { path: '/test-cases', element: <TestCasesPage /> },
      { path: '/test-plans', element: <TestPlansPage /> },
      { path: '/reports', element: <ReportsPage /> },
      { path: '/coverage', element: <CoveragePage /> },
      { path: '/api-docs', element: <ApiDocsPage /> },
      { path: '/scheduled-tasks', element: <ScheduledTasksPage /> },
      { path: '/mock-service', element: <MockServicePage /> },
      { path: '/history', element: <HistoryPage /> },
      { path: '/ai', element: <AIPage /> },
      { path: '/ui-test-cases', element: <UiTestCasesPage /> },
      { path: '/ui-test-suites', element: <UiTestSuitesPage /> },
      { path: '/step-library', element: <StepLibraryPage /> },
      { path: '/ui-elements', element: <UiElementsPage /> },
      { path: '/ui-test-records', element: <UiTestRecordsPage /> },
      { path: '/ui-test-logs', element: <UiTestLogsPage /> },
      { path: '/perf-tests', element: <PerformanceTestPage /> },
      { path: '/perf-reports', element: <PerformanceReportPage /> },
      { path: '/perf-dashboard', element: <PerfDashboardPage /> },
      { path: '/users', element: <UsersPage /> },
      { path: '/roles', element: <RolesPage /> },
      { path: '/api-tokens', element: <ApiTokensPage /> },
      { path: '/ci-cd', element: <CiCdPage /> },
      { path: '/test-data', element: <TestDataPage /> },
      { path: '/notifications', element: <NotificationsPage /> },
      { path: '/knowledge/defects', element: <DefectPatternsPage /> },
      { path: '/knowledge/rules', element: <BusinessRulesPage /> },
      { path: '/knowledge/interfaces', element: <InterfaceKnowledgePage /> },
      { path: '/audit-logs', element: <AuditLogsPage /> },
      { path: '/ai-ops', element: <AiOpsPage /> },
      { path: '/quality-gates', element: <QualityGatesPage /> },
      { path: '/defects', element: <DefectsPage /> },
      { path: '*', element: <Navigate to="/dashboard" replace /> },
    ],
  },
];
