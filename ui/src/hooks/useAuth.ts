import { useState, useEffect } from 'react';
import api from '../services/api';

interface User {
  id: number;
  username: string;
  role: number;
}

export const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);

  const login = async (username: string, password: string) => {
    const resp = await api.post('/api/v1/auth/login', { username, password });
    const token = resp.data.access_token;
    localStorage.setItem('token', token);

    // Decode JWT payload to get user info
    const payload = JSON.parse(atob(token.split('.')[1]));
    const userId = parseInt(payload.sub);

    // Fetch full user details
    const userResp = await api.get('/api/v1/auth/me');
    setUser(userResp.data);
  };

  const logout = () => {
    localStorage.removeItem('token');
    delete api.defaults.headers.common['Authorization'];
    setUser(null);
  };

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      // Fetch current user details
      api.get('/api/v1/auth/me')
        .then(resp => setUser(resp.data))
        .catch(() => {
          // Token invalid, clear it
          localStorage.removeItem('token');
          setUser(null);
        });
    }
  }, []);

  return { user, login, logout };
};
