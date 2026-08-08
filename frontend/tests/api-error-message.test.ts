import axios from 'axios';
import { afterEach, describe, expect, it } from 'vitest';
import apiClient from '../src/api';

const originalAdapter = apiClient.defaults.adapter;

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe('shared API error messages', () => {
  it('shows a backend business message instead of the generic Axios status text', async () => {
    apiClient.defaults.adapter = async (config) => {
      throw new axios.AxiosError('Request failed with status code 413', 'ERR_BAD_REQUEST', config, undefined, {
        data: { code: 413, message: '请求内容过大，请按页面提示缩小文件或文本后重试' },
        status: 413,
        statusText: 'Payload Too Large',
        headers: {},
        config,
      });
    };

    await expect(apiClient.post('/normative/duplication-detections', {})).rejects.toMatchObject({
      message: '请求内容过大，请按页面提示缩小文件或文本后重试',
    });
  });
});
