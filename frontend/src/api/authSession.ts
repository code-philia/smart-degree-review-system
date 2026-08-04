import apiClient from './index';

export type AuthRole = 'STUDENT' | 'SUPERVISOR' | 'SCHOOL_ADMIN' | 'COLLEGE_ADMIN';

export type AuthenticatedUser = {
  id: string;
  username: string;
  role: AuthRole;
  collegeId: string | null;
  supervisorId: string | null;
  scope: 'COLLEGE' | 'SCHOOL';
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type SessionResponse = {
  user: AuthenticatedUser;
};

export async function loginWithLocalAccount(payload: LoginRequest): Promise<SessionResponse> {
  const response = await apiClient.post<SessionResponse>('/auth/login', payload);
  return response.data;
}

export async function fetchCurrentSession(): Promise<SessionResponse> {
  const response = await apiClient.get<SessionResponse>('/auth/me');
  return response.data;
}

export async function logoutCurrentSession(): Promise<void> {
  await apiClient.post('/auth/logout');
}
