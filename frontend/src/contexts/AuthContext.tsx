import axios from 'axios';
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';

// ---------------------------------------------------------------------------
// 类型定义（与后端 schemas/auth.py 对齐）
// ---------------------------------------------------------------------------
export interface RoleInfo {
  id: string;
  name: string;
  description?: string;
  permissions: string[];
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UserInfo {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  roles: RoleInfo[];
  created_at?: string;
  updated_at?: string;
}

export interface TokenData {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  detail?: string;
}

interface PageData<T = any> extends ApiResponse<T[]> {
  total: number;
  page: number;
  page_size: number;
}

export interface UserCreatePayload {
  username: string;
  email: string;
  password: string;
  is_active?: boolean;
  is_superuser?: boolean;
}

export interface UserUpdatePayload {
  username?: string;
  email?: string;
  password?: string;
  is_active?: boolean;
  is_superuser?: boolean;
}

export interface RoleCreatePayload {
  name: string;
  description?: string;
  permissions?: string[];
  is_active?: boolean;
}

export interface RoleUpdatePayload {
  name?: string;
  description?: string;
  permissions?: string[];
  is_active?: boolean;
}

// ---------------------------------------------------------------------------
// 认证专用 axios 实例（自动附加 JWT 令牌）
// 与 services/api.ts 配置保持一致，由独立实例承载认证相关请求。
// ---------------------------------------------------------------------------
const authClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截器：附加 Bearer 令牌
authClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：统一提取 data，与 services/api.ts 行为一致
authClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.message || error.message || '请求失败';
    return Promise.reject(new Error(msg));
  }
);

const TOKEN_KEY = 'access_token';

// ---------------------------------------------------------------------------
// 认证 / 用户 / 角色 API
// ---------------------------------------------------------------------------
export const authApi = {
  // 认证
  login: (username: string, password: string) =>
    authClient.post<unknown, ApiResponse<TokenData>>('/auth/login', {
      username,
      password,
    }),
  getMe: () => authClient.get<unknown, ApiResponse<UserInfo>>('/auth/me'),
  register: (data: UserCreatePayload) =>
    authClient.post<unknown, ApiResponse<UserInfo>>('/auth/register', data),
  // 用户管理
  listUsers: (params?: { page?: number; page_size?: number; keyword?: string }) =>
    authClient.get<unknown, PageData<UserInfo>>('/users', { params }),
  createUser: (data: UserCreatePayload) =>
    authClient.post<unknown, ApiResponse<UserInfo>>('/users', data),
  updateUser: (id: string, data: UserUpdatePayload) =>
    authClient.put<unknown, ApiResponse<UserInfo>>(`/users/${id}`, data),
  deleteUser: (id: string) =>
    authClient.delete<unknown, ApiResponse<UserInfo>>(`/users/${id}`),
  assignRoles: (userId: string, roleIds: string[]) =>
    authClient.post<unknown, ApiResponse<UserInfo>>(`/users/${userId}/roles`, {
      role_ids: roleIds,
    }),
  // 角色管理
  listRoles: (params?: { page?: number; page_size?: number; keyword?: string }) =>
    authClient.get<unknown, PageData<RoleInfo>>('/roles', { params }),
  listAllRoles: () =>
    authClient.get<unknown, ApiResponse<RoleInfo[]>>('/roles/all'),
  createRole: (data: RoleCreatePayload) =>
    authClient.post<unknown, ApiResponse<RoleInfo>>('/roles', data),
  updateRole: (id: string, data: RoleUpdatePayload) =>
    authClient.put<unknown, ApiResponse<RoleInfo>>(`/roles/${id}`, data),
  deleteRole: (id: string) =>
    authClient.delete<unknown, ApiResponse<RoleInfo>>(`/roles/${id}`),
};

// ---------------------------------------------------------------------------
// 认证上下文
// ---------------------------------------------------------------------------
interface AuthContextValue {
  user: UserInfo | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(TOKEN_KEY)
  );
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const res = await authApi.getMe();
      setUser(res.data);
    } catch {
      logout();
    }
  }, [logout]);

  // 启动时若有令牌则拉取用户信息
  useEffect(() => {
    if (token) {
      refreshUser().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token, refreshUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await authApi.login(username, password);
      const t = res.data.access_token;
      localStorage.setItem(TOKEN_KEY, t);
      setToken(t);
      setUser(res.data.user);
    },
    []
  );

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth 必须在 AuthProvider 内部使用');
  }
  return ctx;
}
