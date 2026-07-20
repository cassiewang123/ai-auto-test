import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useAuth } from './AuthContext';
import { environmentApi, projectApi } from '../services/api';
import type { Environment, Project } from '../types';

const PROJECT_STORAGE_KEY = 'airetest.selectedProjectId';
const ENVIRONMENT_STORAGE_KEY = 'airetest.selectedEnvironmentId';

export interface WorkspaceContextValue {
  projects: Project[];
  environments: Environment[];
  selectedProjectId: string | null;
  selectedEnvironmentId: string | null;
  setSelectedProjectId: (projectId: string | null) => void;
  setSelectedEnvironmentId: (environmentId: string | null) => void;
  loading: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(
  undefined
);

function readStoredId(key: string): string | null {
  return localStorage.getItem(key);
}

function persistId(key: string, value: string | null): void {
  if (value) {
    localStorage.setItem(key, value);
  } else {
    localStorage.removeItem(key);
  }
}

function resolveProjectId(projects: Project[]): string | null {
  const storedId = readStoredId(PROJECT_STORAGE_KEY);
  return (
    projects.find((project) => project.id === storedId)?.id ??
    projects[0]?.id ??
    null
  );
}

function resolveEnvironmentId(environments: Environment[]): string | null {
  const storedId = readStoredId(ENVIRONMENT_STORAGE_KEY);
  return (
    environments.find((environment) => environment.id === storedId)?.id ??
    environments.find((environment) => environment.is_active)?.id ??
    environments[0]?.id ??
    null
  );
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [selectedProjectId, setSelectedProjectIdState] = useState<string | null>(
    null
  );
  const [
    selectedEnvironmentId,
    setSelectedEnvironmentIdState,
  ] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (authLoading) {
      setLoading(true);
      return;
    }

    if (!user) {
      setProjects([]);
      setEnvironments([]);
      setSelectedProjectIdState(null);
      setSelectedEnvironmentIdState(null);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);

    Promise.allSettled([
      projectApi.listAll(),
      environmentApi.list({ page: 1, page_size: 100 }),
    ])
      .then(([projectsResult, environmentsResult]) => {
        if (!active) {
          return;
        }

        if (projectsResult.status === 'fulfilled') {
          const projectList = projectsResult.value.data || [];
          const projectId = resolveProjectId(projectList);
          setProjects(projectList);
          setSelectedProjectIdState(projectId);
          persistId(PROJECT_STORAGE_KEY, projectId);
        }

        if (environmentsResult.status === 'fulfilled') {
          const environmentList = environmentsResult.value.data || [];
          const environmentId = resolveEnvironmentId(environmentList);
          setEnvironments(environmentList);
          setSelectedEnvironmentIdState(environmentId);
          persistId(ENVIRONMENT_STORAGE_KEY, environmentId);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [authLoading, user]);

  const setSelectedProjectId = useCallback((projectId: string | null) => {
    setSelectedProjectIdState(projectId);
    persistId(PROJECT_STORAGE_KEY, projectId);
  }, []);

  const setSelectedEnvironmentId = useCallback(
    (environmentId: string | null) => {
      setSelectedEnvironmentIdState(environmentId);
      persistId(ENVIRONMENT_STORAGE_KEY, environmentId);
    },
    []
  );

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      projects,
      environments,
      selectedProjectId,
      selectedEnvironmentId,
      setSelectedProjectId,
      setSelectedEnvironmentId,
      loading,
    }),
    [
      projects,
      environments,
      selectedProjectId,
      selectedEnvironmentId,
      setSelectedProjectId,
      setSelectedEnvironmentId,
      loading,
    ]
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace 必须在 WorkspaceProvider 内部使用');
  }
  return context;
}
