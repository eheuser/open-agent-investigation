// ui/src/pages/Playbooks.tsx
import React, { useState, useEffect } from 'react';
import {
  BookOpenIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  DocumentDuplicateIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
  CheckIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline';
import PlaybookEditor from '../components/playbooks/PlaybookEditor';
import PlaybookViewer from '../components/playbooks/PlaybookViewer';
import {
  getPlaybooks,
  createPlaybook,
  updatePlaybook,
  deletePlaybook,
  clonePlaybook,
  Playbook,
  BasePlaybook,
  PlaybookListResponse,
  AnyPlaybook,
  isBasePlaybook,
} from '../services/playbooks';

const Playbooks: React.FC = () => {
  const [playbooks, setPlaybooks] = useState<PlaybookListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPlaybook, setSelectedPlaybook] = useState<AnyPlaybook | null>(null);
  const [viewMode, setViewMode] = useState<'list' | 'view' | 'edit' | 'create'>('list');
  const [editingPlaybook, setEditingPlaybook] = useState<Playbook | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadPlaybooks();
  }, []);

  const loadPlaybooks = async () => {
    try {
      setLoading(true);
      const data = await getPlaybooks();
      setPlaybooks(data);
      setError(null);
    } catch (err: any) {
      console.error('Failed to load playbooks:', err);
      setError(err.message || 'Failed to load playbooks');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (data: { name: string; description: string; playbook: string }) => {
    try {
      setActionLoading(true);
      await createPlaybook(data);
      await loadPlaybooks();
      setViewMode('list');
      setError(null);
    } catch (err: any) {
      console.error('Failed to create playbook:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to create playbook');
      throw err;
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdate = async (id: number, data: { name?: string; description?: string; playbook?: string; is_enabled?: boolean }) => {
    try {
      setActionLoading(true);
      await updatePlaybook(id, data);
      await loadPlaybooks();
      setViewMode('list');
      setEditingPlaybook(null);
      setError(null);
    } catch (err: any) {
      console.error('Failed to update playbook:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to update playbook');
      throw err;
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      setActionLoading(true);
      await deletePlaybook(id);
      await loadPlaybooks();
      setDeleteConfirmId(null);
      setError(null);
    } catch (err: any) {
      console.error('Failed to delete playbook:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to delete playbook');
    } finally {
      setActionLoading(false);
    }
  };

  const handleClone = async (sourceName: string) => {
    try {
      setActionLoading(true);
      await clonePlaybook(sourceName);
      await loadPlaybooks();
      setError(null);
    } catch (err: any) {
      console.error('Failed to clone playbook:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to clone playbook');
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleEnabled = async (playbook: Playbook) => {
    try {
      await updatePlaybook(playbook.playbook_id, { is_enabled: !playbook.is_enabled });
      await loadPlaybooks();
    } catch (err: any) {
      console.error('Failed to toggle playbook:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to toggle playbook');
    }
  };

  const handleView = (playbook: AnyPlaybook) => {
    setSelectedPlaybook(playbook);
    setViewMode('view');
  };

  const handleEdit = (playbook: Playbook) => {
    setEditingPlaybook(playbook);
    setViewMode('edit');
  };

  const handleBack = () => {
    setViewMode('list');
    setSelectedPlaybook(null);
    setEditingPlaybook(null);
  };

  // Filter playbooks based on search query
  const filterPlaybooks = (items: AnyPlaybook[]) => {
    if (!searchQuery.trim()) return items;

    const query = searchQuery.toLowerCase();
    return items.filter(
      (p) =>
        p.name.toLowerCase().includes(query) ||
        p.description.toLowerCase().includes(query)
    );
  };

  const filteredBasePlaybooks: BasePlaybook[] = playbooks ? filterPlaybooks(playbooks.base_playbooks) as BasePlaybook[] : [];
  const filteredUserPlaybooks: Playbook[] = playbooks ? filterPlaybooks(playbooks.user_playbooks) as Playbook[] : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-200 dark:border-blue-900 border-t-blue-600 dark:border-t-blue-400 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Loading playbooks...</p>
        </div>
      </div>
    );
  }

  if (viewMode === 'view' && selectedPlaybook) {
    const handleEditClick = !isBasePlaybook(selectedPlaybook) ? () => handleEdit(selectedPlaybook as Playbook) : undefined;
    const handleCloneClick = isBasePlaybook(selectedPlaybook) ? () => handleClone(selectedPlaybook.name) : undefined;

    return (
      <PlaybookViewer
        playbook={selectedPlaybook}
        onBack={handleBack}
        onEdit={handleEditClick}
        onClone={handleCloneClick}
      />
    );
  }

  if (viewMode === 'edit' && editingPlaybook) {
    return (
      <PlaybookEditor
        mode="edit"
        initialData={editingPlaybook}
        onSave={(data) => handleUpdate(editingPlaybook.playbook_id, data)}
        onCancel={handleBack}
        loading={actionLoading}
      />
    );
  }

  if (viewMode === 'create') {
    return (
      <PlaybookEditor
        mode="create"
        onSave={handleCreate}
        onCancel={handleBack}
        loading={actionLoading}
      />
    );
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BookOpenIcon className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">Investigation Playbooks</h1>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {playbooks?.total || 0} playbooks ({playbooks?.base_playbooks.length || 0} base, {playbooks?.user_playbooks.length || 0} custom)
              </p>
            </div>
          </div>

          <button
            onClick={() => setViewMode('create')}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            <PlusIcon className="w-5 h-5" />
            <span>Create Playbook</span>
          </button>
        </div>

        {/* Search Bar */}
        <div className="mt-4 relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search playbooks by name or description..."
            className="w-full pl-10 pr-10 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <XMarkIcon className="w-5 h-5" />
            </button>
          )}
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

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {/* Base Playbooks Section */}
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <span className="inline-flex items-center px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 text-xs font-medium rounded">
              Base
            </span>
            <span>Built-in Playbooks</span>
            <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
              ({filteredBasePlaybooks.length})
            </span>
          </h2>

          {filteredBasePlaybooks.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {searchQuery ? 'No base playbooks match your search' : 'No base playbooks available'}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredBasePlaybooks.map((playbook) => (
                <PlaybookCard
                  key={playbook.name}
                  playbook={playbook}
                  onView={() => handleView(playbook)}
                  onClone={() => handleClone(playbook.name)}
                  loading={actionLoading}
                />
              ))}
            </div>
          )}
        </section>

        {/* User Playbooks Section */}
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <span className="inline-flex items-center px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200 text-xs font-medium rounded">
              Custom
            </span>
            <span>Your Playbooks</span>
            <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
              ({filteredUserPlaybooks.length})
            </span>
          </h2>

          {filteredUserPlaybooks.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {searchQuery ? 'No custom playbooks match your search' : 'No custom playbooks yet. Create one or clone a base playbook to get started.'}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredUserPlaybooks.map((playbook) => (
                <PlaybookCard
                  key={playbook.playbook_id}
                  playbook={playbook}
                  onView={() => handleView(playbook)}
                  onEdit={() => handleEdit(playbook)}
                  onDelete={() => setDeleteConfirmId(playbook.playbook_id)}
                  onToggleEnabled={() => handleToggleEnabled(playbook)}
                  loading={actionLoading}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Delete Playbook
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to delete this playbook? This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteConfirmId(null)}
                disabled={actionLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                disabled={actionLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {actionLoading ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Playbook Card Component
interface PlaybookCardProps {
  playbook: AnyPlaybook;
  onView: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  onClone?: () => void;
  onToggleEnabled?: () => void;
  loading?: boolean;
}

const PlaybookCard: React.FC<PlaybookCardProps> = ({
  playbook,
  onView,
  onEdit,
  onDelete,
  onClone,
  onToggleEnabled,
  loading,
}) => {
  const isBase = isBasePlaybook(playbook);
  const isEnabled = isBase ? true : (playbook as Playbook).is_enabled;

  return (
    <div className={`bg-white dark:bg-gray-800 border rounded-lg p-4 hover:shadow-lg transition-shadow ${!isEnabled ? 'opacity-60' : ''
      } ${isBase ? 'border-blue-200 dark:border-blue-800' : 'border-gray-200 dark:border-gray-700'}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 dark:text-white truncate">
            {playbook.name}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            {isBase ? (
              <span className="inline-flex items-center px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 text-xs font-medium rounded">
                Base
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200 text-xs font-medium rounded">
                Custom
              </span>
            )}
            {!isEnabled && (
              <span className="inline-flex items-center px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs font-medium rounded">
                Disabled
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">
        {playbook.description}
      </p>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onView}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors text-sm"
        >
          <EyeIcon className="w-4 h-4" />
          <span>View</span>
        </button>

        {onClone && (
          <button
            onClick={onClone}
            disabled={loading}
            className="flex items-center justify-center gap-2 px-3 py-2 bg-blue-100 dark:bg-blue-900/30 hover:bg-blue-200 dark:hover:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded-lg transition-colors text-sm disabled:opacity-50"
            title="Clone to custom playbooks"
          >
            <DocumentDuplicateIcon className="w-4 h-4" />
          </button>
        )}

        {onEdit && (
          <button
            onClick={onEdit}
            className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors text-sm"
            title="Edit playbook"
          >
            <PencilIcon className="w-4 h-4" />
          </button>
        )}

        {onToggleEnabled && (
          <button
            onClick={onToggleEnabled}
            className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${isEnabled
                ? 'bg-green-100 dark:bg-green-900/30 hover:bg-green-200 dark:hover:bg-green-900/50 text-green-700 dark:text-green-300'
                : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300'
              }`}
            title={isEnabled ? 'Disable playbook' : 'Enable playbook'}
          >
            {isEnabled ? <EyeIcon className="w-4 h-4" /> : <EyeSlashIcon className="w-4 h-4" />}
          </button>
        )}

        {onDelete && (
          <button
            onClick={onDelete}
            disabled={loading}
            className="flex items-center justify-center gap-2 px-3 py-2 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 text-red-700 dark:text-red-300 rounded-lg transition-colors text-sm disabled:opacity-50"
            title="Delete playbook"
          >
            <TrashIcon className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};

export default Playbooks;
