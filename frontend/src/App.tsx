import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import DashboardPage from './pages/DashboardPage';
import QuickTestPage from './pages/QuickTestPage';
import ApiListPage from './pages/ApiListPage';
import ImportPage from './pages/ImportPage';
import ProjectsPage from './pages/ProjectsPage';
import EnvironmentsPage from './pages/EnvironmentsPage';
import GlobalVariablesPage from './pages/GlobalVariablesPage';
import TestCasesPage from './pages/TestCasesPage';
import TestPlansPage from './pages/TestPlansPage';
import ReportsPage from './pages/ReportsPage';
import CoveragePage from './pages/CoveragePage';
import ApiDocsPage from './pages/ApiDocsPage';
import ScheduledTasksPage from './pages/ScheduledTasksPage';
import MockServicePage from './pages/MockServicePage';
import HistoryPage from './pages/HistoryPage';
import AIPage from './pages/AIPage';
import UiTestCasesPage from './pages/UiTestCasesPage';
import UiTestSuitesPage from './pages/UiTestSuitesPage';
import StepLibraryPage from './pages/StepLibraryPage';
import UiElementsPage from './pages/UiElementsPage';
import UiTestRecordsPage from './pages/UiTestRecordsPage';
import UiTestLogsPage from './pages/UiTestLogsPage';
import PerformanceTestPage from './pages/PerformanceTestPage';
import PerformanceReportPage from './pages/PerformanceReportPage';
import PerfDashboardPage from './pages/PerfDashboardPage';
import LoginPage from './pages/LoginPage';
import UsersPage from './pages/UsersPage';
import RolesPage from './pages/RolesPage';
import ApiTokensPage from './pages/ApiTokensPage';
import CiCdPage from './pages/CiCdPage';
import TestDataPage from './pages/TestDataPage';
import NotificationsPage from './pages/NotificationsPage';
import DefectPatternsPage from './pages/DefectPatternsPage';
import BusinessRulesPage from './pages/BusinessRulesPage';
import InterfaceKnowledgePage from './pages/InterfaceKnowledgePage';
import JobsPage from './pages/JobsPage';
import AuditLogsPage from './pages/AuditLogsPage';
import AiOpsPage from './pages/AiOpsPage';
import QualityGatesPage from './pages/QualityGatesPage';
import DefectsPage from './pages/DefectsPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppLayout />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/quick-test" element={<QuickTestPage />} />
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
  );
}
