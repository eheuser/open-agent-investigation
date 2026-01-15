import React, { useState, useEffect } from 'react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
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
  // Embedding configuration (optional - required for RAG)
  embedding_provider?: string | null;
  embedding_api_url?: string | null;
  embedding_api_key_masked?: string;
  embedding_model_name?: string | null;
  created_at: string;
  updated_at: string;
}

const Settings: React.FC = () => {
  const [configs, setConfigs] = useState<LLMConfig[]>([]);
  const [activeConfig, setActiveConfig] = useState<LLMConfig | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [configToDelete, setConfigToDelete] = useState<number | null>(null);

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
    // Embedding configuration
    embedding_provider: '' as string | undefined,
    embedding_api_url: 'http://host.docker.internal:1234/v1/embeddings' as string | undefined,
    embedding_api_key: '' as string | undefined,
    embedding_model_name: '' as string | undefined,
  });

  useEffect(() => {
    loadConfigs();
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
      // Embedding configuration
      embedding_provider: config.embedding_provider ?? '',
      embedding_api_url: config.embedding_api_url ?? '',
      embedding_api_key: '', // Don't populate for security
      embedding_model_name: config.embedding_model_name ?? '',
    });
  };

  const resetForm = () => {
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
      // Embedding configuration
      embedding_provider: '',
      embedding_api_url: 'http://host.docker.internal:1234/v1/embeddings',
      embedding_api_key: '',
      embedding_model_name: '',
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
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            {showCreateForm ? 'Cancel' : '+ Add Configuration'}
          </button>
        </div>

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
            <ConfigForm formData={formData} setFormData={setFormData} />
            <div className="flex gap-2 mt-4">
              <button
                type="submit"
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg"
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
                className={`p-4 rounded-lg ${
                  config.is_active
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
}> = ({ formData, setFormData }) => (
  <div className="grid grid-cols-2 gap-4">
    <div>
      <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
        Provider Name
      </label>
      <input
        type="text"
        value={formData.provider_name}
        onChange={(e) => setFormData({ ...formData, provider_name: e.target.value })}
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
        onChange={(e) => setFormData({ ...formData, model_name: e.target.value })}
        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
        required
      />
    </div>
    <div className="col-span-2">
      <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
        API Endpoint
      </label>
      <input
        type="url"
        value={formData.api_endpoint}
        onChange={(e) => setFormData({ ...formData, api_endpoint: e.target.value })}
        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
        required
      />
    </div>
    <div className="col-span-2">
      <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
        API Key
      </label>
      <input
        type="password"
        value={formData.api_key}
        onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
        placeholder="Leave empty to keep existing key"
      />
    </div>
    <div>
      <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
        Max Context Length
      </label>
      <input
        type="number"
        value={formData.max_context_length}
        onChange={(e) =>
          setFormData({ ...formData, max_context_length: parseInt(e.target.value) })
        }
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
        onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
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
        onChange={(e) => setFormData({ ...formData, timeout: parseInt(e.target.value) })}
        min="1"
        max="3600"
        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
        required
      />
    </div>
    
    {/* Embedding Configuration Section */}
    <div className="col-span-2 mt-6 pt-6 border-t border-gray-300 dark:border-gray-600">
      <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
        Embedding Configuration (Optional - Required for RAG)
      </h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Embedding Provider
          </label>
          <select
            value={formData.embedding_provider || ''}
            onChange={(e) => setFormData({ ...formData, embedding_provider: e.target.value || undefined })}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
          >
            <option value="">None (RAG disabled)</option>
            <option value="openai">OpenAI</option>
            <option value="cohere">Cohere</option>
            <option value="ollama">Ollama</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Embedding Model
          </label>
          <input
            type="text"
            value={formData.embedding_model_name || ''}
            onChange={(e) => setFormData({ ...formData, embedding_model_name: e.target.value || undefined })}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            placeholder="e.g., text-embedding-ada-002"
          />
        </div>
        <div className="col-span-2">
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Embedding API URL
          </label>
          <input
            type="url"
            value={formData.embedding_api_url || ''}
            onChange={(e) => setFormData({ ...formData, embedding_api_url: e.target.value || undefined })}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            placeholder="e.g., http://host.docker.internal:1234/v1/embeddings"
          />
        </div>
        <div className="col-span-2">
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Embedding API Key
          </label>
          <input
            type="password"
            value={formData.embedding_api_key || ''}
            onChange={(e) => setFormData({ ...formData, embedding_api_key: e.target.value || undefined })}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-600 dark:text-white"
            placeholder="Leave empty to keep existing key"
          />
        </div>
      </div>
    </div>
  </div>
);

// Config Card Component
const ConfigCard: React.FC<{
  config: LLMConfig;
  onEdit: (config: LLMConfig) => void;
  onDelete: (id: number) => void;
  onSetActive: (id: number) => void;
  isEditing: boolean;
  formData: any;
  setFormData: (data: any) => void;
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
  onUpdate,
  onCancelEdit,
}) => {
  if (isEditing) {
    return (
      <div>
        <ConfigForm formData={formData} setFormData={setFormData} />
        <div className="flex gap-2 mt-4">
          <button
            onClick={() => onUpdate(config.config_id)}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg"
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
              <span className="font-medium text-gray-700 dark:text-gray-300">Model:</span>{' '}
              <span className="text-gray-900 dark:text-white">{config.embedding_model_name || 'N/A'}</span>
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
