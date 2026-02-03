import { useState, useEffect } from 'react';
import api from '../services/api';

interface LLMConfigStatus {
  hasConfig: boolean;
  isLoading: boolean;
  error: string | null;
  checkConfig: () => Promise<boolean>;
}

export const useLLMConfig = (): LLMConfigStatus => {
  const [hasConfig, setHasConfig] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkConfig = async (): Promise<boolean> => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await api.get('/api/v1/llm-config/active');
      const hasValidConfig = Boolean(response.data);
      setHasConfig(hasValidConfig);
      return hasValidConfig;
    } catch (err: any) {
      if (err.response?.status === 404) {
        setHasConfig(false);
        setError('No active LLM configuration found');
        return false;
      }
      setError(err.response?.data?.detail || 'Failed to check LLM configuration');
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkConfig();
  }, []);

  return { hasConfig, isLoading, error, checkConfig };
};
