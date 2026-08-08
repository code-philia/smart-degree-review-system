import apiClient from './index';

export type DuplicationCorpusSourceType = 'paste' | 'file';

export type DuplicationCorpusSample = {
  id: string;
  title: string;
  subject: string;
  year: number;
  content: string;
  source_type: DuplicationCorpusSourceType;
  source_filename?: string | null;
  created_by: string;
  created_at: string;
};

export type CreateDuplicationCorpusSampleRequest = {
  title: string;
  subject: string;
  year: number;
  content: string;
  source_type: DuplicationCorpusSourceType;
  source_filename?: string | null;
};

export async function fetchDuplicationCorpusSamples(): Promise<DuplicationCorpusSample[]> {
  const response = await apiClient.get<{ samples: DuplicationCorpusSample[] }>('/normative/duplication-corpus');
  return response.data.samples;
}

export async function createDuplicationCorpusSample(
  payload: CreateDuplicationCorpusSampleRequest,
): Promise<DuplicationCorpusSample> {
  const response = await apiClient.post<DuplicationCorpusSample>('/normative/duplication-corpus', payload, {
    timeout: 310_000,
  });
  return response.data;
}

export async function deleteDuplicationCorpusSample(sampleId: string): Promise<void> {
  await apiClient.delete(`/normative/duplication-corpus/${sampleId}`);
}
