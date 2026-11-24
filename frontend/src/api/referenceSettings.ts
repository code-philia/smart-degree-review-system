import apiClient from './index';

export type ReferenceSettingsStatus = {
  configured: boolean;
  key_hint: string | null;
  storage_available: boolean;
  serpapi_configured: boolean;
  serpapi_key_hint: string | null;
  secure_transport_required: boolean;
};

export type ReferenceProvider = 'openalex' | 'serpapi';

// Deliberately select only public status fields; never retain a raw key response.
function publicStatus(data: ReferenceSettingsStatus): ReferenceSettingsStatus {
  return {
    configured: data.configured === true,
    key_hint: typeof data.key_hint === 'string' ? data.key_hint : null,
    storage_available: data.storage_available === true,
    serpapi_configured: data.serpapi_configured === true,
    serpapi_key_hint: typeof data.serpapi_key_hint === 'string' ? data.serpapi_key_hint : null,
    secure_transport_required: data.secure_transport_required === true,
  };
}

export async function fetchReferenceSettings(signal: AbortSignal) {
  const response = await apiClient.get<ReferenceSettingsStatus>('/auth/reference-settings', { signal });
  return publicStatus(response.data);
}

export async function saveReferenceKey(
  userId: string,
  apiKey: string,
  signal: AbortSignal,
  provider: ReferenceProvider = 'openalex',
) {
  const field = provider === 'serpapi' ? 'serpapi_key' : 'api_key';
  const response = await apiClient.put<ReferenceSettingsStatus>(
    '/auth/reference-settings',
    { [field]: apiKey, expected_user_id: userId },
    { signal },
  );
  return publicStatus(response.data);
}

export async function removeReferenceKey(
  userId: string,
  signal: AbortSignal,
  provider: ReferenceProvider = 'openalex',
) {
  const data = provider === 'serpapi' ? { provider, expected_user_id: userId } : { expected_user_id: userId };
  const response = await apiClient.delete<ReferenceSettingsStatus>('/auth/reference-settings', { data, signal });
  return publicStatus(response.data);
}
