/**
 * Status Modal - System statistics and health monitoring
 * Displays on-demand system stats with refresh capabilities
 */
import React, { useState, useEffect } from 'react';
import {
  XMarkIcon,
  ArrowPathIcon,
  ChartBarIcon,
  DocumentTextIcon,
  FolderIcon,
  CpuChipIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import api from '../services/api';

interface StatusModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface SystemStats {
  investigations: {
    total: number;
    detailed: Array<{
      investigation_id: string;
      title: string;
      owner: string;
      created_at: string;
      total_events: number;
      events_with_embeddings: number;
      events_without_embeddings: number;
      event_embedding_coverage_percent: number;
      total_timeline_entries: number;
      timeline_with_embeddings: number;
      timeline_without_embeddings: number;
      timeline_embedding_coverage_percent: number;
    }>;
  };
  artifacts: {
    total: number;
    total_size_bytes: number;
    total_size_mb: number;
    by_classification: Array<{ classification: string; count: number }>;
    list: Array<{
      artifact_id: number;
      filename: string;
      classification: string;
      upload_ts: string;
      size_bytes: number;
      investigation_title: string;
      sha256: string;
    }>;
    search_total: number;
    page: number;
    page_size: number;
    total_pages: number;
    has_more: boolean;
  };
  events: {
    total: number;
    events_with_embeddings: number;
    events_without_embeddings: number;
    embedding_coverage_percent: number;
    by_type: Array<{ event_type: string; count: number }>;
    by_investigation: Array<{
      investigation_id: string;
      title: string;
      event_count: number;
    }>;
  };
  embeddings: {
    total: number;
    by_owner_type: Array<{ owner_type: string; count: number }>;
    by_model: Array<{ model_name: string; count: number }>;
  };
  timeline: {
    total: number;
    by_type: Array<{ entry_type: string; count: number }>;
    with_embeddings: number;
    embedding_coverage_percent: number;
  };
  jobs: {
    parsing: {
      pending: number;
      running: number;
      completed: number;
      failed: number;
    };
    agents: {
      pending: number;
      running: number;
      completed: number;
      failed: number;
    };
    embedding: {
      pending: number;
      running: number;
      completed: number;
      failed: number;
    };
  };
  users: {
    total: number;
    admins: number;
    regular: number;
  };
  database: {
    status: string;
    message?: string;
  };
}

const StatusModal: React.FC<StatusModalProps> = ({ isOpen, onClose }) => {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState<
    'overview' | 'investigations' | 'artifacts' | 'events' | 'jobs'
  >('overview');
  const [artifactsSearch, setArtifactsSearch] = useState('');
  const [artifactsPage, setArtifactsPage] = useState(1);
  const [artifactsPageSize] = useState(20);

  useEffect(() => {
    if (isOpen && !stats) {
      fetchStats();
    }
  }, [isOpen]);

  // Refetch when artifacts pagination/search changes
  useEffect(() => {
    if (isOpen && stats) {
      fetchStats();
    }
  }, [artifactsPage, artifactsSearch]);

  const handleArtifactsSearch = (search: string) => {
    setArtifactsSearch(search);
    setArtifactsPage(1); // Reset to page 1 on new search
  };

  const fetchStats = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get('/api/v1/system/status', {
        params: {
          artifacts_page: artifactsPage,
          artifacts_page_size: artifactsPageSize,
          artifacts_search: artifactsSearch,
        },
      });
      setStats(response.data);
      setLastRefresh(new Date());
    } catch (err: any) {
      console.error('Failed to fetch system status:', err);
      setError(err.response?.data?.detail || 'Failed to fetch system status');
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const getClassificationName = (classification: string): string => {
    const names: Record<string, string> = {
      '0': 'System Hive',
      '1': 'Log File',
      '2': 'Binary',
      '3': 'Archive',
      '4': 'Unknown',
    };
    return names[classification] || classification;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="relative w-full max-w-6xl bg-white dark:bg-gray-800 rounded-lg shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-6 py-4">
            <div className="flex items-center gap-3">
              <ChartBarIcon className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                  System Status
                </h2>
                {lastRefresh && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Last updated: {lastRefresh.toLocaleTimeString()}
                  </p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchStats}
                disabled={loading}
                className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                title="Refresh statistics"
              >
                <ArrowPathIcon
                  className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`}
                />
              </button>
              <button
                onClick={onClose}
                className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="border-b border-gray-200 dark:border-gray-700 px-6">
            <nav className="flex gap-4">
              {[
                { id: 'overview', label: 'Overview' },
                { id: 'investigations', label: 'Investigations' },
                { id: 'artifacts', label: 'Artifacts' },
                { id: 'events', label: 'Events & Embeddings' },
                { id: 'jobs', label: 'Jobs' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id
                      ? 'border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                    }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="px-6 py-4 h-[600px] overflow-y-auto">
            {loading && !stats && (
              <div className="flex items-center justify-center h-full">
                <ArrowPathIcon className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300">
                <ExclamationTriangleIcon className="w-5 h-5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {stats && (
              <>
                {/* Overview Tab */}
                {activeTab === 'overview' && (
                  <div className="space-y-6">
                    {/* Database Health */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <CpuChipIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                          Database Health
                        </h3>
                      </div>
                      <div className="flex items-center gap-2">
                        {stats.database.status === 'connected' ? (
                          <>
                            <CheckCircleIcon className="w-5 h-5 text-green-600 dark:text-green-400" />
                            <span className="text-green-700 dark:text-green-300 font-medium">
                              Connected
                            </span>
                          </>
                        ) : (
                          <>
                            <ExclamationTriangleIcon className="w-5 h-5 text-red-600 dark:text-red-400" />
                            <span className="text-red-700 dark:text-red-300 font-medium">
                              {stats.database.status}
                            </span>
                          </>
                        )}
                        {stats.database.message && (
                          <span className="text-sm text-gray-600 dark:text-gray-400">
                            - {stats.database.message}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Quick Stats Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <StatCard
                        icon={<FolderIcon className="w-5 h-5" />}
                        label="Investigations"
                        value={stats.investigations.total}
                        color="blue"
                      />
                      <StatCard
                        icon={<ChartBarIcon className="w-5 h-5" />}
                        label="Events"
                        value={stats.events.total}
                        subtitle={`${stats.events.embedding_coverage_percent}% embedded`}
                        color="purple"
                      />
                      <StatCard
                        icon={<ClockIcon className="w-5 h-5" />}
                        label="Timeline Entries"
                        value={stats.timeline.total}
                        subtitle={`${stats.timeline.embedding_coverage_percent}% embedded`}
                        color="orange"
                      />
                    </div>

                    {/* Users */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                        Users
                      </h3>
                      <div className="grid grid-cols-3 gap-4 text-sm">
                        <div>
                          <div className="text-gray-500 dark:text-gray-400">Total</div>
                          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                            {stats.users.total}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-500 dark:text-gray-400">Admins</div>
                          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                            {stats.users.admins}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-500 dark:text-gray-400">Regular</div>
                          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                            {stats.users.regular}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Investigations Tab */}
                {activeTab === 'investigations' && (
                  <div className="space-y-4">
                    {stats.investigations.detailed.length === 0 ? (
                      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                        No investigations found
                      </div>
                    ) : (
                      stats.investigations.detailed.map((inv) => (
                        <div
                          key={inv.investigation_id}
                          className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700"
                        >
                          {/* Header */}
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1 min-w-0">
                              <h4 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                                {inv.title}
                              </h4>
                              <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                                <span>Owner: {inv.owner}</span>
                                <span>•</span>
                                <span>Created: {formatDate(inv.created_at)}</span>
                              </div>
                            </div>
                          </div>

                          {/* Stats Grid */}
                          <div className="grid grid-cols-2 gap-4 mt-4">
                            {/* Events */}
                            <div className="space-y-2">
                              <div className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase">
                                Events
                              </div>
                              <div className="flex items-baseline gap-2">
                                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                  {inv.total_events.toLocaleString()}
                                </span>
                                <span className="text-sm text-gray-500 dark:text-gray-400">total</span>
                              </div>
                              <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-600 dark:text-gray-400">With embeddings</span>
                                <span className="font-medium text-green-600 dark:text-green-400">
                                  {inv.events_with_embeddings.toLocaleString()}
                                </span>
                              </div>
                              <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-600 dark:text-gray-400">Coverage</span>
                                <span className="font-medium text-blue-600 dark:text-blue-400">
                                  {inv.event_embedding_coverage_percent}%
                                </span>
                              </div>
                              {/* Progress bar */}
                              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-2">
                                <div
                                  className="bg-blue-600 dark:bg-blue-400 h-1.5 rounded-full transition-all"
                                  style={{
                                    width: `${inv.event_embedding_coverage_percent}%`,
                                  }}
                                />
                              </div>
                            </div>

                            {/* Timeline */}
                            <div className="space-y-2">
                              <div className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase">
                                Timeline
                              </div>
                              <div className="flex items-baseline gap-2">
                                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                  {inv.total_timeline_entries.toLocaleString()}
                                </span>
                                <span className="text-sm text-gray-500 dark:text-gray-400">entries</span>
                              </div>
                              <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-600 dark:text-gray-400">With embeddings</span>
                                <span className="font-medium text-green-600 dark:text-green-400">
                                  {inv.timeline_with_embeddings.toLocaleString()}
                                </span>
                              </div>
                              <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-600 dark:text-gray-400">Coverage</span>
                                <span className="font-medium text-purple-600 dark:text-purple-400">
                                  {inv.timeline_embedding_coverage_percent}%
                                </span>
                              </div>
                              {/* Progress bar */}
                              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-2">
                                <div
                                  className="bg-purple-600 dark:bg-purple-400 h-1.5 rounded-full transition-all"
                                  style={{
                                    width: `${inv.timeline_embedding_coverage_percent}%`,
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* Artifacts Tab */}
                {activeTab === 'artifacts' && (
                  <div className="space-y-4">
                    {/* Search Bar */}
                    <div className="relative">
                      <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                      <input
                        type="text"
                        value={artifactsSearch}
                        onChange={(e) => handleArtifactsSearch(e.target.value)}
                        placeholder="Search artifacts by filename..."
                        className="w-full pl-10 pr-4 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
                      />
                    </div>

                    {/* Artifacts List */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                          Artifacts
                          {artifactsSearch && (
                            <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                              (filtered: {stats.artifacts.search_total.toLocaleString()} results)
                            </span>
                          )}
                        </h3>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          Page {stats.artifacts.page} of {stats.artifacts.total_pages}
                        </div>
                      </div>

                      {stats.artifacts.list.length === 0 ? (
                        <div className="text-center py-8 text-gray-500 dark:text-gray-400 text-sm">
                          {artifactsSearch ? 'No artifacts match your search' : 'No artifacts found'}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {stats.artifacts.list.map((artifact) => (
                            <div
                              key={artifact.artifact_id}
                              className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0">
                                  <div className="font-medium text-gray-900 dark:text-gray-100 truncate text-sm">
                                    {artifact.filename}
                                  </div>
                                  <div className="flex items-center gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    <span className="px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 font-medium">
                                      {getClassificationName(artifact.classification)}
                                    </span>
                                    <span>•</span>
                                    <span>{artifact.investigation_title}</span>
                                  </div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    Uploaded: {formatDate(artifact.upload_ts)}
                                  </div>
                                  {artifact.sha256 && (
                                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 font-mono truncate">
                                      SHA256: {artifact.sha256}
                                    </div>
                                  )}
                                </div>
                                <div className="text-sm font-medium text-gray-600 dark:text-gray-400 flex-shrink-0">
                                  {formatBytes(artifact.size_bytes)}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Pagination */}
                      {stats.artifacts.total_pages > 1 && (
                        <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                          <button
                            onClick={() => setArtifactsPage(Math.max(1, artifactsPage - 1))}
                            disabled={artifactsPage === 1 || loading}
                            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            <ChevronLeftIcon className="w-4 h-4" />
                            Previous
                          </button>

                          <span className="text-sm text-gray-600 dark:text-gray-400">
                            Page {stats.artifacts.page} of {stats.artifacts.total_pages}
                          </span>

                          <button
                            onClick={() => setArtifactsPage(Math.min(stats.artifacts.total_pages, artifactsPage + 1))}
                            disabled={!stats.artifacts.has_more || loading}
                            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            Next
                            <ChevronRightIcon className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Events & Embeddings Tab */}
                {activeTab === 'events' && (
                  <div className="space-y-6">
                    {/* Embedding Coverage */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                        Event Embedding Coverage
                      </h3>
                      <div className="grid grid-cols-3 gap-4 mb-4">
                        <div>
                          <div className="text-gray-500 dark:text-gray-400 text-sm">
                            Total Events
                          </div>
                          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                            {stats.events.total}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-500 dark:text-gray-400 text-sm">
                            With Embeddings
                          </div>
                          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                            {stats.events.events_with_embeddings}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-500 dark:text-gray-400 text-sm">
                            Coverage
                          </div>
                          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                            {stats.events.embedding_coverage_percent}%
                          </div>
                        </div>
                      </div>
                      {/* Progress bar */}
                      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all"
                          style={{
                            width: `${stats.events.embedding_coverage_percent}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Events by Type */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                        Top Event Types
                      </h3>
                      <div className="space-y-2 max-h-64 overflow-y-auto">
                        {stats.events.by_type.slice(0, 15).map((item, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between text-sm"
                          >
                            <span className="text-gray-700 dark:text-gray-300 font-mono text-xs">
                              {item.event_type}
                            </span>
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {item.count.toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Embedding Models */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                        Embedding Models Used
                      </h3>
                      <div className="space-y-2">
                        {stats.embeddings.by_model.map((item, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between text-sm"
                          >
                            <span className="text-gray-700 dark:text-gray-300">
                              {item.model_name}
                            </span>
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {item.count.toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Embeddings by Owner Type */}
                    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                        Embeddings by Type
                      </h3>
                      <div className="space-y-2">
                        {stats.embeddings.by_owner_type.map((item, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between text-sm"
                          >
                            <span className="text-gray-700 dark:text-gray-300 capitalize">
                              {item.owner_type}
                            </span>
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {item.count.toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Jobs Tab */}
                {activeTab === 'jobs' && (
                  <div className="space-y-6">
                    <JobStatusCard title="Parsing Jobs" jobs={stats.jobs.parsing} />
                    <JobStatusCard title="Agent Jobs" jobs={stats.jobs.agents} />
                    <JobStatusCard title="Embedding Jobs" jobs={stats.jobs.embedding} />
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-gray-200 dark:border-gray-700 px-6 py-4">
            <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
              <span>Open Agent Investigation v1.0</span>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Stat Card Component
interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  subtitle?: string;
  color: 'blue' | 'green' | 'purple' | 'orange';
}

const StatCard: React.FC<StatCardProps> = ({ icon, label, value, subtitle, color }) => {
  const colorClasses = {
    blue: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20',
    green: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20',
    purple: 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20',
    orange: 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20',
  };

  return (
    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
      <div className={`inline-flex p-2 rounded-lg ${colorClasses[color]} mb-2`}>
        {icon}
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        {value.toLocaleString()}
      </div>
      <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
      {subtitle && (
        <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">{subtitle}</div>
      )}
    </div>
  );
};

// Job Status Card Component
interface JobStatusCardProps {
  title: string;
  jobs: {
    pending: number;
    running: number;
    completed: number;
    failed: number;
  };
}

const JobStatusCard: React.FC<JobStatusCardProps> = ({ title, jobs }) => {
  const total = jobs.pending + jobs.running + jobs.completed + jobs.failed;

  return (
    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">{title}</h3>
      <div className="grid grid-cols-4 gap-4 text-sm">
        <div>
          <div className="text-gray-500 dark:text-gray-400">Pending</div>
          <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
            {jobs.pending}
          </div>
        </div>
        <div>
          <div className="text-gray-500 dark:text-gray-400">Running</div>
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
            {jobs.running}
          </div>
        </div>
        <div>
          <div className="text-gray-500 dark:text-gray-400">Completed</div>
          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
            {jobs.completed}
          </div>
        </div>
        <div>
          <div className="text-gray-500 dark:text-gray-400">Failed</div>
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">
            {jobs.failed}
          </div>
        </div>
      </div>
      <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
        Total: {total.toLocaleString()} jobs
      </div>
    </div>
  );
};

export default StatusModal;
