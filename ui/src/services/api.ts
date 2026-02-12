import axios from 'axios';

const instance = axios.create({
  baseURL: '/'
});

// Add request interceptor to include JWT token
instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle auth errors
instance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Don't auto-redirect if this is the initial auth check (useAuth handles it)
      const isAuthCheck = error.config?.url?.includes('/api/v1/auth/me');

      if (!isAuthCheck) {
        // Clear token and redirect to login (but not if already on login page)
        localStorage.removeItem('token');
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

export default instance;
