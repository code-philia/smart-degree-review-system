import apiClient from './index';

export type CompilerRuntimeState = {
  freeze: boolean;
  generation: number;
  active_version: string | null;
  active_path: string | null;
};

export async function fetchCompilerRuntimeState(): Promise<CompilerRuntimeState> {
  const response = await apiClient.get<CompilerRuntimeState>('/normative/paper-lint/control', { timeout: 60_000 });
  return response.data;
}

export async function setCompilerFreeze(freeze: boolean): Promise<CompilerRuntimeState> {
  const response = await apiClient.put<CompilerRuntimeState>('/normative/paper-lint/control/freeze', { freeze }, { timeout: 60_000 });
  return response.data;
}
