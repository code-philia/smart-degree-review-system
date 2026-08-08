import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 5000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const data: unknown = error.response?.data;
      if (typeof data === 'object' && data !== null && 'message' in data && typeof data.message === 'string') {
        const message = data.message.trim();
        if (message) {
          error.message = message;
        }
      }
    }
    return Promise.reject(error);
  },
);

export default apiClient;
