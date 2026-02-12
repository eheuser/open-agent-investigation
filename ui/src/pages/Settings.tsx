import React, { useState, useEffect } from 'react';
import {
  ExclamationTriangleIcon,
  InformationCircleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import { useLocation } from 'react-router-dom';
import api from '../services/api';

interface LLMConfig {
  config_id: number;
  user_id: number;
  provider_name: string;
  api_endpoint: string;
  api_key_masked: string;
  model_name: string;
  max_context_length: number;
  temperature: number;
  top_p?: number | null;
  top_k?: number | null;
  min_p?: number | null;
  timeout: number;
  is_active: boolean;
  allow_concurrent_llm_calls: boolean;
  // Embedding configuration (optional - required for RAG)
  embedding_provider?: string | null;
  embedding_api_url?: string | null;
  embedding_api_key_masked?: string;
  embedding_model_name?: string | null;
  embedding_max_context_length?: number | null;
  reranker_model_name?: string | null;
  reranker_max_context_length?: number | null;
  allow_concurrent_embedding_calls: boolean;
  created_at: string;
  updated_at: string;
}

interface TestResult {
  llm: 'untested' | 'testing' | 'success' | 'failed';
  embedding: 'untested' | 'testing' | 'success' | 'failed';
  llmMessage?: string;
  embeddingMessage?: string;
}

const INTERNET_API_PROVIDERS = ['openai', 'google', 'anthropic', 'openrouter'];

const Settings: React.FC = () => {
  const location = useLocation();
  const [configs, setConfigs] = useState<LLMConfig[]>([]);
  const [activeConfig, setActiveConfig] = useState<LLMConfig | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [configToDelete, setConfigToDelete] = useState<number | null>(null);
  const [showWelcomeBanner, setShowWelcomeBanner] = useState(false);
  const [llmEndpointType, setLlmEndpointType] = useState('localhost');
  const [embeddingEndpointType, setEmbeddingEndpointType] = useState('localhost');
  const [testResult, setTestResult] = useState<TestResult>({
    llm: 'untested',
    embedding: 'untested',
  });

  const [formData, setFormData] = useState({
    provider_name: 'local',
    api_endpoint: 'http://host.docker.internal:1234/v1/chat/completions',
    api_key: '',
    model_name: 'openai/gpt-oss-20b',
    max_context_length: 131072,
    temperature: 1.0,
    top_p: undefined as number | undefined,
    top_k: undefined as number | undefined,
    min_p: undefined as number | undefined,
    timeout: 300,
    is_active: true,
    allow_concurrent_llm_calls: false,
    // Embedding configuration
    embedding_provider: '' as string | undefined,
    embedding_api_url: '' as string | undefined,
    embedding_api_key: '' as string | undefined,
    embedding_model_name: '' as string | undefined,
    embedding_max_context_length: 8192,
    reranker_model_name: '' as string | undefined,
    reranker_max_context_length: 8192,
    allow_concurrent_embedding_calls: false,
  });

  useEffect(() => {
    loadConfigs();

    // Check if user was redirected here from login due to missing config
    // Show welcome banner if no configs exist
    const checkWelcome = async () => {
      try {
        const response = await api.get('/api/v1/llm-config/');
        if (!response.data || response.data.length === 0) {
          setShowWelcomeBanner(true);
        }
      } catch (err) {
        // If error, assume no configs
        setShowWelcomeBanner(true);
      }
    };

    checkWelcome();
  }, []);

  const loadConfigs = async () => {
    try {
      setLoading(true);
      const [configsResp, activeResp] = await Promise.allSettled([
        api.get('/api/v1/llm-config/'),
        api.get('/api/v1/llm-config/active'),
      ]);

      if (configsResp.status === 'fulfilled') {
        setConfigs(configsResp.value.data);
      }

      if (activeResp.status === 'fulfilled') {
        setActiveConfig(activeResp.value.data);
      }

      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load configurations');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/api/v1/llm-config/', formData);
      setShowCreateForm(false);
      resetForm();
      await loadConfigs();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create configuration');
    }
  };

  const handleUpdate = async (configId: number) => {
    try {
      await api.patch(`/api/v1/llm-config/${configId}`, formData);
      setEditingId(null);
      resetForm();
      await loadConfigs();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update configuration');
    }
  };

  const handleDeleteClick = (configId: number) => {
    setConfigToDelete(configId);
    setDeleteModalOpen(true);
  };

  const confirmDelete = async () => {
    if (!configToDelete) return;

    try {
      await api.delete(`/api/v1/llm-config/${configToDelete}`);
      await loadConfigs();
      setDeleteModalOpen(false);
      setConfigToDelete(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete configuration');
      setDeleteModalOpen(false);
      setConfigToDelete(null);
    }
  };

  const cancelDelete = () => {
    setDeleteModalOpen(false);
    setConfigToDelete(null);
  };

  const handleSetActive = async (configId: number) => {
    try {
      await api.patch(`/api/v1/llm-config/${configId}`, { is_active: true });
      await loadConfigs();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to activate configuration');
    }
  };

  const startEdit = (config: LLMConfig) => {
    setEditingId(config.config_id);
    setTestResult({ llm: 'untested', embedding: 'untested' });

    // Detect endpoint type for LLM
    if (config.api_endpoint.includes('api.openai.com')) {
      setLlmEndpointType('openai');
    } else if (config.api_endpoint.includes('generativelanguage.googleapis.com') || config.api_endpoint.includes('aiplatform.googleapis.com')) {
      setLlmEndpointType('google');
    } else if (config.api_endpoint.includes('api.anthropic.com')) {
      setLlmEndpointType('anthropic');
    } else if (config.api_endpoint.includes('openrouter.ai')) {
      setLlmEndpointType('openrouter');
    } else if (config.api_endpoint.includes('host.docker.internal') || config.api_endpoint.includes('localhost')) {
      setLlmEndpointType('localhost');
    } else {
      setLlmEndpointType('custom');
    }

    // Detect endpoint type for embeddings
    if (config.embedding_api_url?.includes('api.openai.com')) {
      setEmbeddingEndpointType('openai');
    } else if (config.embedding_api_url?.includes('generativelanguage.googleapis.com') || config.embedding_api_url?.includes('aiplatform.googleapis.com')) {
      setEmbeddingEndpointType('google');
    } else if (config.embedding_api_url?.includes('api.cohere.ai')) {
      setEmbeddingEndpointType('cohere');
    } else if (config.embedding_api_url?.includes('openrouter.ai')) {
      setEmbeddingEndpointType('openrouter');
    } else if (config.embedding_api_url?.includes('host.docker.internal') || config.embedding_api_url?.includes('localhost')) {
      setEmbeddingEndpointType('localhost');
    } else {
      setEmbeddingEndpointType('custom');
    }

    setFormData({
      provider_name: config.provider_name,
      api_endpoint: config.api_endpoint,
      api_key: '', // Don't populate for security
      model_name: config.model_name,
      max_context_length: config.max_context_length,
      temperature: config.temperature,
      top_p: config.top_p ?? undefined,
      top_k: config.top_k ?? undefined,
      min_p: config.min_p ?? undefined,
      timeout: config.timeout,
      is_active: config.is_active,
      allow_concurrent_llm_calls: config.allow_concurrent_llm_calls,
      // Embedding configuration
      embedding_provider: config.embedding_provider ?? '',
      embedding_api_url: config.embedding_api_url ?? '',
      embedding_api_key: '', // Don't populate for security
      embedding_model_name: config.embedding_model_name ?? '',
      embedding_max_context_length: config.embedding_max_context_length ?? 8192,
      reranker_model_name: config.reranker_model_name ?? '',
      reranker_max_context_length: config.reranker_max_context_length ?? 8192,
      allow_concurrent_embedding_calls: config.allow_concurrent_embedding_calls,
    });
  };

  const resetForm = () => {
    setLlmEndpointType('localhost');
    setEmbeddingEndpointType('localhost');
    setTestResult({ llm: 'untested', embedding: 'untested' });
    setFormData({
      provider_name: 'local',
      api_endpoint: 'http://host.docker.internal:1234/v1/chat/completions',
      api_key: '',
      model_name: 'openai/gpt-oss-20b',
      max_context_length: 131072,
      temperature: 1.0,
      top_p: undefined,
      top_k: undefined,
      min_p: undefined,
      timeout: 300,
      is_active: true,
      allow_concurrent_llm_calls: false,
      // Embedding configuration
      embedding_provider: '',
      embedding_api_url: '',
      embedding_api_key: '',
      embedding_model_name: '',
      embedding_max_context_length: 8192,
      reranker_model_name: '',
      reranker_max_context_length: 8192,
      allow_concurrent_embedding_calls: false,
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500 dark:text-gray-400">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6 bg-white dark:bg-gray-800">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            LLM Provider Settings
          </h1>
          <button
            onClick={() => {
              setShowCreateForm(!showCreateForm);
              if (!showCreateForm) {
                setTestResult({ llm: 'untested', embedding: 'untested' });
              }
            }}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            {showCreateForm ? 'Cancel' : '+ Add Configuration'}
          </button>
        </div>

        {/* Instructions */}
        <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Configuration Requirements
          </h3>
          <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1.5">
            <li className="flex items-start gap-2">
              <span className="text-red-500 font-bold mt-0.5">*</span>
              <span><strong>LLM Configuration (Required):</strong> An active LLM provider is required for all natural language processing, agent investigations, and chat functionality.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-yellow-600 dark:text-yellow-500 font-bold mt-0.5">•</span>
              <span><strong>Embedding Configuration (Optional):</strong> Configure embeddings to enable RAG (Retrieval-Augmented Generation) for semantic search. Without embeddings, "Augmented Chat" mode will be disabled.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-600 dark:text-blue-400 font-bold mt-0.5">ℹ</span>
              <span><strong>API Keys:</strong> API keys are required for internet-based providers (OpenAI, Anthropic, Google, OpenRouter). Local endpoints (Ollama, LM Studio) typically don't require keys.</span>
            </li>
          </ul>
        </div>

        {showWelcomeBanner && configs.length === 0 && (
          <div className="mb-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-start gap-3">
              <InformationCircleIcon className="w-6 h-6 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">
                  Welcome! Configure Your LLM Provider
                </h3>
                <p className="text-sm text-blue-800 dark:text-blue-200 mb-2">
                  To start using Open Agent Investigation, you need to configure an LLM provider.
                  This allows the system to process natural language queries and perform automated analysis.
                </p>
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  Click <strong>"+ Add Configuration"</strong> above to get started.
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <p className="text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}

        {/* Create Form */}
        {showCreateForm && (
          <form onSubmit={handleCreate} className="mb-6 p-6 bg-gray-50 dark:bg-gray-700 rounded-lg">
            <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
              New LLM Configuration
            </h2>
            <ConfigForm
              formData={formData}
              setFormData={setFormData}
              llmEndpointType={llmEndpointType}
              setLlmEndpointType={setLlmEndpointType}
              embeddingEndpointType={embeddingEndpointType}
              setEmbeddingEndpointType={setEmbeddingEndpointType}
              testResult={testResult}
              setTestResult={setTestResult}
              isEditing={false}
            />
            <div className="flex gap-2 mt-4">
              <button
                type="submit"
                disabled={testResult.llm !== 'success'}
                className={`px-4 py-2 rounded-lg ${testResult.llm === 'success'
                    ? 'bg-green-600 hover:bg-green-700 text-white'
                    : 'bg-gray-400 dark:bg-gray-600 text-gray-200 dark:text-gray-400 cursor-not-allowed'
                  }`}
                title={testResult.llm !== 'success' ? 'Please test settings first' : ''}
              >
                Create
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowCreateForm(false);
                  resetForm();
                }}
                className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Active Configuration */}
        {activeConfig && (
          <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-block w-2 h-2 bg-green-500 rounded-full"></span>
              <h3 className="font-semibold text-gray-900 dark:text-white">Active Configuration</h3>
            </div>
            <ConfigCard
              config={activeConfig}
              onEdit={startEdit}
              onDelete={handleDeleteClick}
              onSetActive={handleSetActive}
              isEditing={editingId === activeConfig.config_id}
              formData={formData}
              setFormData={setFormData}
              llmEndpointType={llmEndpointType}
              setLlmEndpointType={setLlmEndpointType}
              embeddingEndpointType={embeddingEndpointType}
              setEmbeddingEndpointType={setEmbeddingEndpointType}
              testResult={testResult}
              setTestResult={setTestResult}
              onUpdate={handleUpdate}
              onCancelEdit={() => {
                setEditingId(null);
                resetForm();
              }}
            />
          </div>
        )}

        {/* All Configurations */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            All Configurations
          </h2>
          {configs.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              No configurations found. Create one to get started.
            </div>
          ) : (
            configs.map((config) => (
              <div
                key={config.config_id}
                className={`p-4 rounded-lg ${config.is_active
                    ? 'bg-green-50 dark:bg-green-900/10'
                    : 'bg-gray-50 dark:bg-gray-700'
                  }`}
              >
                <ConfigCard
                  config={config}
                  onEdit={startEdit}
                  onDelete={handleDeleteClick}
                  onSetActive={handleSetActive}
                  isEditing={editingId === config.config_id}
                  formData={formData}
                  setFormData={setFormData}
                  llmEndpointType={llmEndpointType}
                  setLlmEndpointType={setLlmEndpointType}
                  embeddingEndpointType={embeddingEndpointType}
                  setEmbeddingEndpointType={setEmbeddingEndpointType}
                  testResult={testResult}
                  setTestResult={setTestResult}
                  onUpdate={handleUpdate}
                  onCancelEdit={() => {
                    setEditingId(null);
                    resetForm();
                  }}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={cancelDelete}
          />

          {/* Modal */}
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Delete LLM Configuration
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  Are you sure you want to delete this LLM configuration? This action cannot be undone.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={cancelDelete}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmDelete}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Config Form Component
const ConfigForm: React.FC<{
  formData: any;
  setFormData: (data: any) => void;
  llmEndpointType: string;
  setLlmEndpointType: (type: string) => void;
  embeddingEndpointType: string;
  setEmbeddingEndpointType: (type: string) => void;
  testResult: TestResult;
  setTestResult: React.Dispatch<React.SetStateAction<TestResult>>;
  isEditing: boolean;
}> = ({
  formData,
  setFormData,
  llmEndpointType,
  setLlmEndpointType,
  embeddingEndpointType,
  setEmbeddingEndpointType,
  testResult,
  setTestResult,
  isEditing
}) => {
    // LLM endpoint presets
    const llmEndpoints: Record<string, string> = {
      openai: 'https://api.openai.com/v1/chat/completions',
      google: 'https://generativelanguage.googleapis.com/v1beta/models/',
      anthropic: 'https://api.anthropic.com/v1/messages',
      openrouter: 'https://openrouter.ai/api/v1/chat/completions',
      localhost: 'http://host.docker.internal:1234/v1/chat/completions',
      custom: formData.api_endpoint,
    };

    // Embedding endpoint presets
    const embeddingEndpoints: Record<string, string> = {
      openai: 'https://api.openai.com/v1/embeddings',
      google: 'https://generativelanguage.googleapis.com/v1beta/models/',
      cohere: 'https://api.cohere.ai/v1/embed',
      openrouter: 'https://openrouter.ai/api/v1/embeddings',
      localhost: 'http://host.docker.internal:1234/v1/embeddings',
      custom: formData.embedding_api_url || '',
    };

    // Handle LLM endpoint type change
    const handleLlmEndpointTypeChange = (type: string) => {
      setLlmEndpointType(type);
      if (type !== 'custom') {
        setFormData({ ...formData, api_endpoint: llmEndpoints[type] });
      }
      // Reset test result when configuration changes
      const newResult: TestResult = { ...testResult, llm: 'untested' };
      setTestResult(newResult);
    };

    // Handle embedding endpoint type change
    const handleEmbeddingEndpointTypeChange = (type: string) => {
      setEmbeddingEndpointType(type);
      if (type !== 'custom') {
        setFormData({ ...formData, embedding_api_url: embeddingEndpoints[type] });
      }
      // Reset test result when configuration changes
      const newResult: TestResult = { ...testResult, embedding: 'untested' };
      setTestResult(newResult);
    };

    // Validation helpers
    const isInternetProvider = (type: string) => INTERNET_API_PROVIDERS.includes(type);
    const llmApiKeyRequired = isInternetProvider(llmEndpointType) && !formData.api_key && !isEditing;
    const embeddingApiKeyRequired = formData.embedding_provider &&
      isInternetProvider(embeddingEndpointType) &&
      !formData.embedding_api_key &&
      !isEditing;

    // Check if LLM config has minimum required fields
    const isLLMValid = Boolean(
      formData.provider_name &&
      formData.api_endpoint &&
      formData.model_name &&
      (!isInternetProvider(llmEndpointType) || formData.api_key || isEditing)
    );

    // Check if embedding config has minimum required fields
    // Valid ONLY if all required fields are filled (provider, endpoint type, API URL, model, and API key for internet providers)
    const isEmbeddingValid = Boolean(
      formData.embedding_provider &&
      formData.embedding_provider !== '' &&
      embeddingEndpointType &&  // Provider Type is required
      formData.embedding_api_url &&
      formData.embedding_api_url !== '' &&
      formData.embedding_model_name &&
      formData.embedding_model_name !== '' &&
      (!isInternetProvider(embeddingEndpointType) || (formData.embedding_api_key && formData.embedding_api_key !== '') || isEditing)
    );

    // Check if any embedding field is filled (for test button logic)
    const hasPartialEmbeddingConfig = Boolean(
      (formData.embedding_provider && formData.embedding_provider !== '') ||
      (formData.embedding_api_url && formData.embedding_api_url !== '') ||
      (formData.embedding_model_name && formData.embedding_model_name !== '') ||
      (formData.embedding_api_key && formData.embedding_api_key !== '')
    );

    // Get missing fields for validation messages
    const getMissingLLMFields = (): string[] => {
      const missing: string[] = [];
      if (llmApiKeyRequired) missing.push('API Key');
      return missing;
    };

    const getMissingEmbeddingFields = (): string[] => {
      const missing: string[] = [];
      if (hasPartialEmbeddingConfig && !isEmbeddingValid) {
        if (!formData.embedding_provider || formData.embedding_provider === '') missing.push('Provider Name');
        if (!formData.embedding_api_url || formData.embedding_api_url === '') missing.push('API URL');
        if (!formData.embedding_model_name || formData.embedding_model_name === '') missing.push('Model Name');
        if (embeddingApiKeyRequired) missing.push('API Key');
      }
      return missing;
    };

    // Test settings function
    const testSettings = async () => {
      // Always test LLM (required)
      // Only test embedding if it's fully configured (all required fields present)
      setTestResult({
        llm: 'testing',
        embedding: isEmbeddingValid ? 'testing' : 'untested'
      });

      // Test LLM
      try {
        const llmResponse = await api.post('/api/v1/llm-config/test', {
          provider_name: formData.provider_name,
          api_endpoint: formData.api_endpoint,
          api_key: formData.api_key || undefined,
          model_name: formData.model_name,
          max_context_length: formData.max_context_length,
          temperature: formData.temperature,
          timeout: formData.timeout,
        });

        if (llmResponse.data.success) {
          setTestResult((prev: TestResult): TestResult => ({ ...prev, llm: 'success' as const, llmMessage: llmResponse.data.message }));
        } else {
          setTestResult((prev: TestResult): TestResult => ({ ...prev, llm: 'failed' as const, llmMessage: llmResponse.data.error }));
        }
      } catch (err: any) {
        setTestResult((prev: TestResult): TestResult => ({
          ...prev,
          llm: 'failed' as const,
          llmMessage: err.response?.data?.detail || 'LLM test failed'
        }));
      }

      // Test embedding ONLY if fully configured (all required fields present)
      if (isEmbeddingValid) {
        try {
          const embeddingResponse = await api.post('/api/v1/llm-config/test-embedding', {
            embedding_provider: formData.embedding_provider,
            embedding_api_url: formData.embedding_api_url,
            embedding_api_key: formData.embedding_api_key || undefined,
            embedding_model_name: formData.embedding_model_name,
          });

          if (embeddingResponse.data.success) {
            setTestResult((prev: TestResult): TestResult => ({ ...prev, embedding: 'success' as const, embeddingMessage: embeddingResponse.data.message }));
          } else {
            setTestResult((prev: TestResult): TestResult => ({ ...prev, embedding: 'failed' as const, embeddingMessage: embeddingResponse.data.error }));
          }
        } catch (err: any) {
          setTestResult((prev: TestResult): TestResult => ({
            ...prev,
            embedding: 'failed' as const,
            embeddingMessage: err.response?.data?.detail || 'Embedding test failed'
          }));
        }
      }
    };

    const missingLLMFields = getMissingLLMFields();
    const missingEmbeddingFields = getMissingEmbeddingFields();

    return (
      <div className="grid grid-cols-2 gap-4">
        {/* LLM Configuration */}
        <div className="col-span-2">
          <h3 className="text-md font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            LLM Configuration
            <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200 px-2 py-1 rounded">
              Required
            </span>
            {isLLMValid ? (
              <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-1 rounded font-semibold flex items-center gap-1">
                <CheckCircleIcon className="w-3 h-3" />
                Valid
              </span>
            ) : (
              <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200 px-2 py-1 rounded font-semibold flex items-center gap-1">
                <XCircleIcon className="w-3 h-3" />
                Invalid
              </span>
            )}
          </h3>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Provider Name
          </label>
          <input
            type="text"
            value={formData.provider_name}
            onChange={(e) => {
              setFormData({ ...formData, provider_name: e.target.value });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Model Name
          </label>
          <input
            type="text"
            value={formData.model_name}
            onChange={(e) => {
              setFormData({ ...formData, model_name: e.target.value });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            LLM Provider Type
          </label>
          <select
            value={llmEndpointType}
            onChange={(e) => handleLlmEndpointTypeChange(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
          >
            <option value="openai">OpenAI</option>
            <option value="google">Google (Gemini/Vertex)</option>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openrouter">OpenRouter</option>
            <option value="localhost">Localhost (Docker)</option>
            <option value="custom">Custom URL</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            API Endpoint
          </label>
          <input
            type="url"
            value={formData.api_endpoint}
            onChange={(e) => {
              setFormData({ ...formData, api_endpoint: e.target.value });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            disabled={llmEndpointType !== 'custom'}
            required
          />
        </div>
        <div className="col-span-2">
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            API Key {isInternetProvider(llmEndpointType) && <span className="text-red-500">*</span>}
          </label>
          <input
            type="password"
            value={formData.api_key}
            onChange={(e) => {
              setFormData({ ...formData, api_key: e.target.value });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            className={`w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white ${llmApiKeyRequired ? 'border-red-500 dark:border-red-500' : ''
              }`}
            placeholder={isEditing ? "Leave empty to keep existing key" : "Enter API key"}
            required={isInternetProvider(llmEndpointType)}
          />
          {llmApiKeyRequired && (
            <p className="text-xs text-red-600 dark:text-red-400 mt-1">
              API key is required for {llmEndpointType} provider
            </p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Max Context Length
          </label>
          <input
            type="number"
            value={formData.max_context_length}
            onChange={(e) => {
              setFormData({ ...formData, max_context_length: parseInt(e.target.value) });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            min="1"
            max="1000000"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Temperature (0.0 - 2.0)
          </label>
          <input
            type="number"
            value={formData.temperature}
            onChange={(e) => {
              setFormData({ ...formData, temperature: parseFloat(e.target.value) });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            min="0"
            max="2"
            step="0.1"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Top P (0.0 - 1.0, optional)
          </label>
          <input
            type="number"
            value={formData.top_p ?? ''}
            onChange={(e) => setFormData({ ...formData, top_p: e.target.value ? parseFloat(e.target.value) : undefined })}
            min="0"
            max="1"
            step="0.01"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            placeholder="Leave empty for default"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Top K (optional, provider-specific)
          </label>
          <input
            type="number"
            value={formData.top_k ?? ''}
            onChange={(e) => setFormData({ ...formData, top_k: e.target.value ? parseInt(e.target.value) : undefined })}
            min="1"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            placeholder="Leave empty for default"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Min P (0.0 - 1.0, optional, provider-specific)
          </label>
          <input
            type="number"
            value={formData.min_p ?? ''}
            onChange={(e) => setFormData({ ...formData, min_p: e.target.value ? parseFloat(e.target.value) : undefined })}
            min="0"
            max="1"
            step="0.01"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            placeholder="Leave empty for default"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Timeout (seconds, 1-3600)
          </label>
          <input
            type="number"
            value={formData.timeout}
            onChange={(e) => {
              setFormData({ ...formData, timeout: parseInt(e.target.value) });
              const newResult: TestResult = { ...testResult, llm: 'untested' };
              setTestResult(newResult);
            }}
            min="1"
            max="3600"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            required
          />
        </div>
        <div className="col-span-2">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.allow_concurrent_llm_calls}
              onChange={(e) => setFormData({ ...formData, allow_concurrent_llm_calls: e.target.checked })}
              className="mt-1 w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
            />
            <div>
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Allow Concurrent LLM Calls
              </span>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Enable parallel LLM requests for high-capacity public APIs (OpenAI, Anthropic, etc.).
                Disable for local endpoints with limited GPU resources (Ollama, LM Studio).
              </p>
            </div>
          </label>
        </div>

        {/* Validation Messages */}
        {missingLLMFields.length > 0 && (
          <div className="col-span-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-start gap-2">
              <ExclamationTriangleIcon className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-800 dark:text-red-200">
                  Missing required fields:
                </p>
                <ul className="text-xs text-red-700 dark:text-red-300 mt-1 list-disc list-inside">
                  {missingLLMFields.map(field => (
                    <li key={field}>{field}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* Embedding Configuration Section */}
        <div className="col-span-2 mt-6 pt-6 border-t border-gray-300 dark:border-gray-600">
          <div className="flex items-start gap-2 mb-4">
            <h3 className="text-md font-semibold text-gray-900 dark:text-white">
              Embedding Configuration
            </h3>
            <span className="text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 px-2 py-1 rounded">
              Optional
            </span>
            {isEmbeddingValid ? (
              <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-1 rounded font-semibold flex items-center gap-1">
                <CheckCircleIcon className="w-3 h-3" />
                Valid
              </span>
            ) : (
              <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200 px-2 py-1 rounded font-semibold flex items-center gap-1">
                <XCircleIcon className="w-3 h-3" />
                Invalid
              </span>
            )}
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Configure embeddings to enable semantic search via RAG (Retrieval-Augmented Generation). Without this, "Augmented Chat" mode will not be available.
          </p>
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded p-3 mb-4">
            <p className="text-xs text-blue-800 dark:text-blue-200 mb-2">
              <strong>💡 Embedding Model (Required for RAG):</strong> Used for initial embedding generation during artifact parsing.
              Choose a smaller/faster model (e.g., <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">text-embedding-3-small</code>) since this runs on all events.
            </p>
            <p className="text-xs text-blue-800 dark:text-blue-200">
              <strong>🎯 Reranker Model (Optional):</strong> If configured with a <em>different</em> model name, enables advanced reranking of top candidates for better relevance.
              Choose a larger/more capable model (e.g., <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">text-embedding-3-large</code>).
              <strong>Leave empty to skip reranking and use vector similarity only.</strong>
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Embedding Provider Type
              </label>
              <select
                value={embeddingEndpointType}
                onChange={(e) => handleEmbeddingEndpointTypeChange(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
              >
                <option value="openai">OpenAI</option>
                <option value="google">Google (Gemini/Vertex)</option>
                <option value="cohere">Cohere</option>
                <option value="openrouter">OpenRouter</option>
                <option value="localhost">Localhost (Docker)</option>
                <option value="custom">Custom URL</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Embedding API URL
              </label>
              <input
                type="url"
                value={formData.embedding_api_url || ''}
                onChange={(e) => {
                  setFormData({ ...formData, embedding_api_url: e.target.value || undefined });
                  const newResult: TestResult = { ...testResult, embedding: 'untested' };
                  setTestResult(newResult);
                }}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                disabled={embeddingEndpointType !== 'custom'}
                placeholder="e.g., http://host.docker.internal:1234/v1/embeddings"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Embedding Provider Name
              </label>
              <select
                value={formData.embedding_provider || ''}
                onChange={(e) => {
                  setFormData({ ...formData, embedding_provider: e.target.value || undefined });
                  const newResult: TestResult = { ...testResult, embedding: 'untested' };
                  setTestResult(newResult);
                }}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
              >
                <option value="">None (RAG disabled)</option>
                <option value="openai">openai</option>
                <option value="cohere">cohere</option>
                <option value="ollama">ollama</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Embedding Model
              </label>
              <input
                type="text"
                value={formData.embedding_model_name || ''}
                onChange={(e) => {
                  setFormData({ ...formData, embedding_model_name: e.target.value || undefined });
                  const newResult: TestResult = { ...testResult, embedding: 'untested' };
                  setTestResult(newResult);
                }}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                placeholder="e.g., text-embedding-3-small"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Embedding Max Tokens
              </label>
              <input
                type="number"
                value={formData.embedding_max_context_length}
                onChange={(e) => setFormData({ ...formData, embedding_max_context_length: parseInt(e.target.value) })}
                min="1"
                max="1000000"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                placeholder="8192"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Reranker Model <span className="text-xs text-gray-500 dark:text-gray-400">(optional)</span>
              </label>
              <input
                type="text"
                value={formData.reranker_model_name || ''}
                onChange={(e) => setFormData({ ...formData, reranker_model_name: e.target.value || undefined })}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                placeholder="Leave empty to skip reranking"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Reranker Max Tokens <span className="text-xs text-gray-500 dark:text-gray-400">(optional)</span>
              </label>
              <input
                type="number"
                value={formData.reranker_max_context_length}
                onChange={(e) => setFormData({ ...formData, reranker_max_context_length: parseInt(e.target.value) })}
                min="1"
                max="1000000"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                placeholder="8192"
                disabled={!formData.reranker_model_name}
              />
            </div>
            <div className="col-span-2">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.allow_concurrent_embedding_calls}
                  onChange={(e) => setFormData({ ...formData, allow_concurrent_embedding_calls: e.target.checked })}
                  className="mt-1 w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
                />
                <div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Allow Concurrent Embedding/Reranking Calls
                  </span>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Enable parallel embedding and reranking requests for high-capacity public APIs.
                    Batches large requests (50+ embeddings, 100+ reranks) into parallel API calls.
                    Disable for local endpoints with limited GPU resources.
                  </p>
                </div>
              </label>
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                Embedding API Key {formData.embedding_provider && isInternetProvider(embeddingEndpointType) && <span className="text-red-500">*</span>}
              </label>
              <input
                type="password"
                value={formData.embedding_api_key || ''}
                onChange={(e) => {
                  setFormData({ ...formData, embedding_api_key: e.target.value || undefined });
                  const newResult: TestResult = { ...testResult, embedding: 'untested' };
                  setTestResult(newResult);
                }}
                className={`w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white ${embeddingApiKeyRequired ? 'border-red-500 dark:border-red-500' : ''
                  }`}
                placeholder={isEditing ? "Leave empty to keep existing key" : "Enter API key"}
              />
              {embeddingApiKeyRequired && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                  API key is required for {embeddingEndpointType} provider
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Test Settings Button */}
        <div className="col-span-2 mt-6 pt-6 border-t border-gray-300 dark:border-gray-600">
          <div className="flex items-start gap-4">
            <button
              type="button"
              onClick={testSettings}
              disabled={
                !isLLMValid ||
                (hasPartialEmbeddingConfig && !isEmbeddingValid) ||
                testResult.llm === 'testing' ||
                testResult.embedding === 'testing'
              }
              className={`px-6 py-3 rounded-lg font-medium flex items-center gap-2 ${!isLLMValid || (hasPartialEmbeddingConfig && !isEmbeddingValid)
                  ? 'bg-gray-400 dark:bg-gray-600 text-gray-200 dark:text-gray-400 cursor-not-allowed'
                  : testResult.llm === 'testing' || testResult.embedding === 'testing'
                    ? 'bg-blue-500 text-white cursor-wait'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }`}
            >
              {testResult.llm === 'testing' || testResult.embedding === 'testing' ? (
                <>
                  <ClockIcon className="w-5 h-5 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <CheckCircleIcon className="w-5 h-5" />
                  Test Settings
                </>
              )}
            </button>

            {/* Test Results */}
            {(testResult.llm !== 'untested' || testResult.embedding !== 'untested') && (
              <div className="flex-1 space-y-3">
                {/* LLM Test Result */}
                {testResult.llm !== 'untested' && (
                  <div className="flex items-start gap-3 p-4 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
                    <div className="flex-shrink-0">
                      {testResult.llm === 'success' && (
                        <div className="w-10 h-10 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                          <CheckCircleIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
                        </div>
                      )}
                      {testResult.llm === 'failed' && (
                        <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                          <XCircleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                        </div>
                      )}
                      {testResult.llm === 'testing' && (
                        <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                          <ClockIcon className="w-6 h-6 text-blue-600 dark:text-blue-400 animate-spin" />
                        </div>
                      )}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
                        LLM Configuration
                      </p>
                      <p className={`text-sm font-medium mb-2 ${testResult.llm === 'success'
                          ? 'text-green-700 dark:text-green-300'
                          : testResult.llm === 'failed'
                            ? 'text-red-700 dark:text-red-300'
                            : 'text-blue-700 dark:text-blue-300'
                        }`}>
                        {testResult.llm === 'success' ? '✓ Test Passed' : testResult.llm === 'failed' ? '✗ Test Failed' : 'Testing...'}
                      </p>
                      {testResult.llmMessage && (
                        <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
                          {testResult.llmMessage}
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Embedding Test Result */}
                {testResult.embedding !== 'untested' && (
                  <div className="flex items-start gap-3 p-4 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
                    <div className="flex-shrink-0">
                      {testResult.embedding === 'success' && (
                        <div className="w-10 h-10 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                          <CheckCircleIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
                        </div>
                      )}
                      {testResult.embedding === 'failed' && (
                        <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                          <XCircleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                        </div>
                      )}
                      {testResult.embedding === 'testing' && (
                        <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                          <ClockIcon className="w-6 h-6 text-blue-600 dark:text-blue-400 animate-spin" />
                        </div>
                      )}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
                        Embedding Configuration
                      </p>
                      <p className={`text-sm font-medium mb-2 ${testResult.embedding === 'success'
                          ? 'text-green-700 dark:text-green-300'
                          : testResult.embedding === 'failed'
                            ? 'text-red-700 dark:text-red-300'
                            : 'text-blue-700 dark:text-blue-300'
                        }`}>
                        {testResult.embedding === 'success' ? '✓ Test Passed' : testResult.embedding === 'failed' ? '✗ Test Failed' : 'Testing...'}
                      </p>
                      {testResult.embeddingMessage && (
                        <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
                          {testResult.embeddingMessage}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Help text */}
          <div className="mt-3 space-y-2">
            {testResult.llm !== 'success' && (
              <p className="text-sm text-gray-600 dark:text-gray-400">
                <strong>Note:</strong> You must test your LLM settings successfully before saving.
              </p>
            )}
            {hasPartialEmbeddingConfig && !isEmbeddingValid && (
              <p className="text-sm text-yellow-700 dark:text-yellow-300">
                <strong>Warning:</strong> Embedding configuration is incomplete. Either fill all required fields or clear them to proceed without RAG.
              </p>
            )}
            {!hasPartialEmbeddingConfig && (
              <p className="text-sm text-gray-600 dark:text-gray-400">
                <strong>Info:</strong> No embedding configuration detected. RAG features will be disabled.
              </p>
            )}
          </div>
        </div>
      </div>
    );
  };

// Config Card Component (same as before, just pass testResult props)
const ConfigCard: React.FC<{
  config: LLMConfig;
  onEdit: (config: LLMConfig) => void;
  onDelete: (id: number) => void;
  onSetActive: (id: number) => void;
  isEditing: boolean;
  formData: any;
  setFormData: (data: any) => void;
  llmEndpointType: string;
  setLlmEndpointType: (type: string) => void;
  embeddingEndpointType: string;
  setEmbeddingEndpointType: (type: string) => void;
  testResult: TestResult;
  setTestResult: React.Dispatch<React.SetStateAction<TestResult>>;
  onUpdate: (id: number) => void;
  onCancelEdit: () => void;
}> = ({
  config,
  onEdit,
  onDelete,
  onSetActive,
  isEditing,
  formData,
  setFormData,
  llmEndpointType,
  setLlmEndpointType,
  embeddingEndpointType,
  setEmbeddingEndpointType,
  testResult,
  setTestResult,
  onUpdate,
  onCancelEdit,
}) => {
    if (isEditing) {
      return (
        <div>
          <ConfigForm
            formData={formData}
            setFormData={setFormData}
            llmEndpointType={llmEndpointType}
            setLlmEndpointType={setLlmEndpointType}
            embeddingEndpointType={embeddingEndpointType}
            setEmbeddingEndpointType={setEmbeddingEndpointType}
            testResult={testResult}
            setTestResult={setTestResult}
            isEditing={true}
          />
          <div className="flex gap-2 mt-4">
            <button
              onClick={() => onUpdate(config.config_id)}
              disabled={testResult.llm !== 'success'}
              className={`px-4 py-2 rounded-lg ${testResult.llm === 'success'
                  ? 'bg-green-600 hover:bg-green-700 text-white'
                  : 'bg-gray-400 dark:bg-gray-600 text-gray-200 dark:text-gray-400 cursor-not-allowed'
                }`}
              title={testResult.llm !== 'success' ? 'Please test settings first' : ''}
            >
              Save
            </button>
            <button
              onClick={onCancelEdit}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg"
            >
              Cancel
            </button>
          </div>
        </div>
      );
    }

    return (
      <div>
        <div className="grid grid-cols-2 gap-4 mb-3 text-sm">
          <div>
            <span className="font-medium text-gray-700 dark:text-gray-300">Provider:</span>{' '}
            <span className="text-gray-900 dark:text-white">{config.provider_name}</span>
          </div>
          <div>
            <span className="font-medium text-gray-700 dark:text-gray-300">Model:</span>{' '}
            <span className="text-gray-900 dark:text-white">{config.model_name}</span>
          </div>
          <div className="col-span-2">
            <span className="font-medium text-gray-700 dark:text-gray-300">Endpoint:</span>{' '}
            <span className="text-gray-900 dark:text-white font-mono text-xs">
              {config.api_endpoint}
            </span>
          </div>
          <div>
            <span className="font-medium text-gray-700 dark:text-gray-300">Context:</span>{' '}
            <span className="text-gray-900 dark:text-white">
              {config.max_context_length.toLocaleString()} tokens
            </span>
          </div>
          <div>
            <span className="font-medium text-gray-700 dark:text-gray-300">Temperature:</span>{' '}
            <span className="text-gray-900 dark:text-white">{config.temperature}</span>
          </div>
          {config.top_p != null && (
            <div>
              <span className="font-medium text-gray-700 dark:text-gray-300">Top P:</span>{' '}
              <span className="text-gray-900 dark:text-white">{config.top_p}</span>
            </div>
          )}
          {config.top_k != null && (
            <div>
              <span className="font-medium text-gray-700 dark:text-gray-300">Top K:</span>{' '}
              <span className="text-gray-900 dark:text-white">{config.top_k}</span>
            </div>
          )}
          {config.min_p != null && (
            <div>
              <span className="font-medium text-gray-700 dark:text-gray-300">Min P:</span>{' '}
              <span className="text-gray-900 dark:text-white">{config.min_p}</span>
            </div>
          )}
          <div>
            <span className="font-medium text-gray-700 dark:text-gray-300">Timeout:</span>{' '}
            <span className="text-gray-900 dark:text-white">{config.timeout}s</span>
          </div>
          <div>
            <span className="font-medium text-gray-700 dark:text-gray-300">Concurrent LLM:</span>{' '}
            <span className="text-gray-900 dark:text-white">{config.allow_concurrent_llm_calls ? 'Enabled' : 'Disabled'}</span>
          </div>
          {config.embedding_provider && (
            <>
              <div className="col-span-2 mt-2 pt-2 border-t border-gray-200 dark:border-gray-600">
                <span className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">Embedding Config (RAG)</span>
              </div>
              <div>
                <span className="font-medium text-gray-700 dark:text-gray-300">Provider:</span>{' '}
                <span className="text-gray-900 dark:text-white">{config.embedding_provider}</span>
              </div>
              <div>
                <span className="font-medium text-gray-700 dark:text-gray-300">Embedding Model:</span>{' '}
                <span className="text-gray-900 dark:text-white">{config.embedding_model_name || 'N/A'}</span>
              </div>
              <div>
                <span className="font-medium text-gray-700 dark:text-gray-300">Embedding Max Tokens:</span>{' '}
                <span className="text-gray-900 dark:text-white">{config.embedding_max_context_length?.toLocaleString() || 'N/A'}</span>
              </div>
              <div>
                <span className="font-medium text-gray-700 dark:text-gray-300">Reranker Model:</span>{' '}
                {config.reranker_model_name && config.reranker_model_name !== config.embedding_model_name ? (
                  <span className="text-gray-900 dark:text-white">
                    {config.reranker_model_name}
                    <span className="ml-2 text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-0.5 rounded">Active</span>
                  </span>
                ) : (
                  <span className="text-gray-500 dark:text-gray-400">
                    Not configured
                    <span className="ml-2 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded">Vector similarity only</span>
                  </span>
                )}
              </div>
              <div>
                <span className="font-medium text-gray-700 dark:text-gray-300">Reranker Max Tokens:</span>{' '}
                <span className="text-gray-900 dark:text-white">{config.reranker_max_context_length?.toLocaleString() || 'N/A'}</span>
              </div>
              <div>
                <span className="font-medium text-gray-700 dark:text-gray-300">Concurrent Embedding:</span>{' '}
                <span className="text-gray-900 dark:text-white">{config.allow_concurrent_embedding_calls ? 'Enabled' : 'Disabled'}</span>
              </div>
              <div className="col-span-2">
                <span className="font-medium text-gray-700 dark:text-gray-300">Endpoint:</span>{' '}
                <span className="text-gray-900 dark:text-white font-mono text-xs">
                  {config.embedding_api_url || 'N/A'}
                </span>
              </div>
            </>
          )}
        </div>
        <div className="flex gap-2">
          {!config.is_active && (
            <button
              onClick={() => onSetActive(config.config_id)}
              className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm rounded"
            >
              Set Active
            </button>
          )}
          <button
            onClick={() => onEdit(config)}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white text-sm rounded"
          >
            Edit
          </button>
          <button
            onClick={() => onDelete(config.config_id)}
            className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-sm rounded"
          >
            Delete
          </button>
        </div>
      </div>
    );
  };

export default Settings;
