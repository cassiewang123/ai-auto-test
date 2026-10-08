import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
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
const TextComparePage = lazy(() => import('./pages/tools/TextComparePage'));
const RegexTesterPage = lazy(() => import('./pages/tools/RegexTesterPage'));
const EncodingPage = lazy(() => import('./pages/tools/EncodingPage'));
const WordCountPage = lazy(() => import('./pages/tools/WordCountPage'));
const TimestampPage = lazy(() => import('./pages/tools/TimestampPage'));
const DataGeneratorPage = lazy(() => import('./pages/tools/DataGeneratorPage'));
const LogAnalysisPage = lazy(() => import('./pages/tools/LogAnalysisPage'));

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
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/quick-test" element={<QuickTestPage />} />
          <Route path="/tools" element={<ToolsHubPage />} />
          <Route path="/tools/json-compare" element={<JsonComparePage />} />
          <Route path="/tools/text-compare" element={<TextComparePage />} />
          <Route path="/tools/regex" element={<RegexTesterPage />} />
          <Route path="/tools/encoding" element={<EncodingPage />} />
          <Route path="/tools/word-count" element={<WordCountPage />} />
          <Route path="/tools/timestamp" element={<TimestampPage />} />
          <Route path="/tools/data-generator" element={<DataGeneratorPage />} />
          <Route path="/tools/log-analysis" element={<LogAnalysisPage />} />
          <Route path="/json-compare" element={<Navigate to="/tools/json-compare" replace />} />
          <Route path="/api-list" element={<ApiListPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/environments" element={<EnvironmentsPage />} />
          <Route path="/variables" element={<GlobalVariablesPage />} />
          <Route path="/test-cases" element={<TestCasesPage />} />
          <Route path="/test-plans" element={<TestPlansPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/coverage" element={<CoveragePage />} />
          <Route path="/api-docs" element={<ApiDocsPage />} />
          <Route path="/scheduled-tasks" element={<ScheduledTasksPage />} />
          <Route path="/mock-service" element={<MockServicePage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/ai" element={<AIPage />} />
          <Route path="/ui-test-cases" element={<UiTestCasesPage />} />
          <Route path="/ui-test-suites" element={<UiTestSuitesPage />} />
          <Route path="/step-library" element={<StepLibraryPage />} />
          <Route path="/ui-elements" element={<UiElementsPage />} />
          <Route path="/ui-test-records" element={<UiTestRecordsPage />} />
          <Route path="/ui-test-logs" element={<UiTestLogsPage />} />
          <Route path="/perf-tests" element={<PerformanceTestPage />} />
          <Route path="/perf-reports" element={<PerformanceReportPage />} />
          <Route path="/perf-dashboard" element={<PerfDashboardPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/roles" element={<RolesPage />} />
          <Route path="/api-tokens" element={<ApiTokensPage />} />
          <Route path="/ci-cd" element={<CiCdPage />} />
          <Route path="/test-data" element={<TestDataPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/knowledge/defects" element={<DefectPatternsPage />} />
          <Route path="/knowledge/rules" element={<BusinessRulesPage />} />
          <Route path="/knowledge/interfaces" element={<InterfaceKnowledgePage />} />
          <Route path="/audit-logs" element={<AuditLogsPage />} />
          <Route path="/ai-ops" element={<AiOpsPage />} />
          <Route path="/quality-gates" element={<QualityGatesPage />} />
          <Route path="/defects" element={<DefectsPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
