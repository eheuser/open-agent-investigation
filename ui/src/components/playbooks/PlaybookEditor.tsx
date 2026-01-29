// ui/src/components/playbooks/PlaybookEditor.tsx
import React, { useState } from 'react';
import { ArrowLeftIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Playbook } from '../../services/playbooks';

interface PlaybookEditorProps {
  mode: 'create' | 'edit';
  initialData?: Playbook;
  onSave: (data: { name: string; description: string; playbook: string }) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

const PlaybookEditor: React.FC<PlaybookEditorProps> = ({
  mode,
  initialData,
  onSave,
  onCancel,
  loading,
}) => {
  const [name, setName] = useState(initialData?.name || '');
  const [description, setDescription] = useState(initialData?.description || '');
  const [playbook, setPlaybook] = useState(initialData?.playbook || '');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validation
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    
    if (!description.trim()) {
      setError('Description is required');
      return;
    }
    
    if (!playbook.trim()) {
      setError('Playbook content is required');
      return;
    }
    
    try {
      setSaving(true);
      setError(null);
      await onSave({ name: name.trim(), description: description.trim(), playbook: playbook.trim() });
    } catch (err: any) {
      setError(err.message || 'Failed to save playbook');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <ArrowLeftIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                {mode === 'create' ? 'Create Playbook' : 'Edit Playbook'}
              </h1>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {mode === 'create' ? 'Create a new investigation playbook' : 'Modify playbook content and metadata'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onCancel}
              disabled={saving || loading}
              className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors disabled:opacity-50"
            >
              <XMarkIcon className="w-5 h-5" />
              <span>Cancel</span>
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving || loading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              <CheckIcon className="w-5 h-5" />
              <span>{saving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-2">
            <XMarkIcon className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
            >
              <XMarkIcon className="w-5 h-5" />
            </button>
          </div>
        )}
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto p-6">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto space-y-6">
          {/* Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., lateral_movement_custom"
              className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Unique identifier for the playbook (lowercase, underscores allowed)
            </p>
          </div>

          {/* Description */}
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Description <span className="text-red-500">*</span>
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of the investigation strategy..."
              rows={3}
              className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Short summary of what this playbook investigates (max 1000 characters)
            </p>
          </div>

          {/* Playbook Content */}
          <div>
            <label htmlFor="playbook" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Playbook Content <span className="text-red-500">*</span>
            </label>
            <textarea
              id="playbook"
              value={playbook}
              onChange={(e) => setPlaybook(e.target.value)}
              placeholder="## Investigation Playbook&#10;&#10;### What to Look For&#10;1. Key indicators...&#10;2. Event types...&#10;&#10;### Investigation Steps&#10;- Query: `query_jsonb_field`..."
              rows={20}
              className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
              required
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Markdown content with investigation steps, queries, and guidance (supports code blocks and formatting)
            </p>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PlaybookEditor;
