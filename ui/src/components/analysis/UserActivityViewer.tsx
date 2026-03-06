import React, { useState, useEffect } from 'react';
import api from '../../services/api';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import TypedDictionaryViewer from '../TypedDictionaryViewer';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClockIcon,
  DocumentTextIcon,
  ArrowPathIcon,
  TrashIcon,
  PlusIcon,
  UserIcon,
  FolderIcon,
  CommandLineIcon,
  MagnifyingGlassCircleIcon,
  DocumentDuplicateIcon,
} from '@heroicons/react/24/outline';

interface Props {
  investigationId: string;
}

interface UserActivityEntry {
  category: string;
  description: string;
  timestamp_meaning: string;
  activity_description: string;
  timestamp?: string;
  event_id?: number;
  artifact_sequence_id?: number;
  user_context?: string;
  additional_data?: { [key: string]: any };
  raw_data?: any;
}

interface UserActivityResponse {
  entries: UserActivityEntry[];
  total: number;
  categories_analyzed: string[];
  summary: { [category: string]: number };
}

interface Category {
  key: string;
  name: string;
  description: string;
  timestamp_meaning: string;
}

const UserActivityViewer: React.FC<Props> = ({ investigationId }) => {
  const [entries, setEntries] = useState<UserActivityEntry[]>([]);
  const [filteredEntries, setFilteredEntries] = useState<UserActivityEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pagination
  const [page, setPage] = useState(0);
  const [pageSize] = useState(50);

  // Filters
  const [searchText, setSearchText] = useState('');
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(true);

  // Available categories
  const [availableCategories, setAvailableCategories] = useState<Category[]>([]);

  // Summary
  const [summary, setSummary] = useState<{ [category: string]: number }>({});

  // Expanded entries
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set());

  // Grouped view
  const [groupBy, setGroupBy] = useState<'category' | 'none'>('category');

  // Clear cache modal
  const [showClearCacheConfirm, setShowClearCacheConfirm] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);

  // Add to timeline
  const [addingToTimeline, setAddingToTimeline] = useState<number | null>(null);
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Load available categories on mount
  useEffect(() => {
    loadCategories();
  }, []);

  // Load user activity data on mount and when categories change
  useEffect(() => {
    loadUserActivity();
  }, [investigationId, selectedCategories]);

  // Subscribe to WebSocket for real-time updates
  const { subscribe } = useWebSocketContext();

  useEffect(() => {
    const handleMessage = (message: any) => {
      if (message.type === 'parsing_complete') {
        loadUserActivity();
      }
    };

    const unsubscribe = subscribe(handleMessage);
    return unsubscribe;
  }, [subscribe, investigationId, selectedCategories]);

  // Apply filters when entries or filter settings change
  useEffect(() => {
    applyFilters();
    setPage(0);
  }, [entries, searchText]);

  const loadCategories = async () => {
    try {
      const response = await api.get<{ categories: Category[]; total: number }>(
        '/api/v1/analysis/user-activity/categories'
      );
      setAvailableCategories(response.data.categories);
    } catch (err: any) {
      console.error('Failed to load categories:', err);
    }
  };

  const loadUserActivity = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      selectedCategories.forEach((cat) => {
        params.append('categories', cat);
      });

      const response = await api.get<UserActivityResponse>(
        `/api/v1/analysis/user-activity/${investigationId}?${params.toString()}`
      );

      setEntries(response.data.entries);
      setSummary(response.data.summary);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load user activity data');
      console.error('Failed to load user activity:', err);
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...entries];

    if (searchText) {
      const searchLower = searchText.toLowerCase();
      filtered = filtered.filter(
        (entry) =>
          entry.activity_description.toLowerCase().includes(searchLower) ||
          entry.category.toLowerCase().includes(searchLower) ||
          entry.description.toLowerCase().includes(searchLower) ||
          (entry.user_context && entry.user_context.toLowerCase().includes(searchLower))
      );
    }

    setFilteredEntries(filtered);
  };

  const toggleCategory = (categoryKey: string) => {
    setSelectedCategories((prev) =>
      prev.includes(categoryKey)
        ? prev.filter((c) => c !== categoryKey)
        : [...prev, categoryKey]
    );
  };

  const toggleEntry = (index: number) => {
    const newExpanded = new Set(expandedEntries);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedEntries(newExpanded);
  };

  const formatTimestamp = (ts?: string) => {
    if (!ts) return 'N/A';
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  const highlightText = (text: string) => {
    if (!searchText || !text) return text;

    const regex = new RegExp(`(${searchText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return String(text).replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-700">$1</mark>');
  };

  const getGroupedEntries = () => {
    if (groupBy === 'none') {
      return { 'All Entries': filteredEntries };
    }

    const grouped: { [key: string]: UserActivityEntry[] } = {};
    filteredEntries.forEach((entry) => {
      const key = entry.category;
      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(entry);
    });

    return grouped;
  };

  const totalPages = Math.ceil(filteredEntries.length / pageSize);
  const paginatedEntries = filteredEntries.slice(page * pageSize, (page + 1) * pageSize);

  const getPaginatedGroupedEntries = () => {
    if (groupBy === 'none') {
      return { 'All Entries': paginatedEntries };
    }

    const grouped: { [key: string]: UserActivityEntry[] } = {};
    paginatedEntries.forEach((entry) => {
      const key = entry.category;
      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(entry);
    });

    return grouped;
  };

  const paginatedGroupedEntries = getPaginatedGroupedEntries();

  const clearCache = async () => {
    setClearingCache(true);
    try {
      await api.delete(`/api/v1/analysis/cache/${investigationId}`);
      setShowClearCacheConfirm(false);
      await loadUserActivity();
    } catch (err: any) {
      console.error('Failed to clear cache:', err);
      setError(err.response?.data?.detail || 'Failed to clear cache');
    } finally {
      setClearingCache(false);
    }
  };

  const addToTimeline = async (entry: UserActivityEntry) => {
    if (!entry.event_id) {
      return;
    }

    setAddingToTimeline(entry.event_id);
    try {
      await api.post(`/api/v1/timeline/${investigationId}/entries`, {
        event_id: entry.event_id,
        timestamp: entry.timestamp || new Date().toISOString(),
        entry_type: 'event',
        title: entry.activity_description,
        description: `Category: ${entry.category}\nTimestamp Meaning: ${entry.timestamp_meaning}`,
      });

      setTimeout(() => {
        setAddingToTimeline(null);
      }, 1000);
    } catch (err: any) {
      console.error('Failed to add to timeline:', err);

      if (err.response?.status === 409) {
        setErrorMessage('This event is already on the timeline');
      } else {
        setErrorMessage(err.response?.data?.detail || err.message || 'Failed to add to timeline');
      }

      setShowErrorModal(true);
      setAddingToTimeline(null);
    }
  };

  // Get icon for category
  const getCategoryIcon = (category: string) => {
    const iconMap: { [key: string]: any } = {
      'ShellBags': FolderIcon,
      'RecentDocs': DocumentDuplicateIcon,
      'OpenSaveMRU': DocumentTextIcon,
      'LastVisitedMRU': DocumentTextIcon,
      'TypedPaths': CommandLineIcon,
      'RunMRU': CommandLineIcon,
      'WordWheelQuery': MagnifyingGlassCircleIcon,
    };
    const Icon = iconMap[category] || UserIcon;
    return <Icon className="w-4 h-4" />;
  };

  return (
    <>
      {/* Error Modal */}
      {showErrorModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className="absolute inset-0"
            onClick={() => setShowErrorModal(false)}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Unable to Add to Timeline
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {errorMessage}
            </p>
            <div className="flex justify-end">
              <button
                onClick={() => setShowErrorModal(false)}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clear Cache Confirmation Modal */}
      {showClearCacheConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className="absolute inset-0"
            onClick={() => !clearingCache && setShowClearCacheConfirm(false)}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Clear Analysis Cache?
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
              This will clear all cached user activity results and force a fresh analysis on the next request. Use this if you've uploaded new artifacts and want to see updated results immediately.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowClearCacheConfirm(false)}
                disabled={clearingCache}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                onClick={clearCache}
                disabled={clearingCache}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {clearingCache ? 'Clearing...' : 'Clear Cache'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col h-full bg-white dark:bg-gray-900">
        {/* Header */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                User Activity Analysis
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Windows user activity artifacts (ShellBags, RecentDocs, OpenSaveMRU, TypedPaths, RunMRU, WordWheelQuery)
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowClearCacheConfirm(true)}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors"
                title="Clear cached results and force fresh analysis"
              >
                <TrashIcon className="w-4 h-4" />
                Clear Cache
              </button>
              <button
                onClick={loadUserActivity}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Analyzing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {/* Search and Filters */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search activity..."
                className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
              />
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${showFilters
                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
            >
              <FunnelIcon className="w-4 h-4" />
              Filters
            </button>
          </div>

          {/* Filter Panel */}
          {showFilters && (
            <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 space-y-3">
              {/* Category Filter */}
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Categories
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {availableCategories
                    .sort((a, b) => (summary[b.key] || 0) - (summary[a.key] || 0))
                    .map((cat) => (
                      <button
                        key={cat.key}
                        onClick={() => toggleCategory(cat.key)}
                        className={`px-3 py-2 rounded-md text-xs font-medium transition-colors text-left min-h-[4.5rem] flex flex-col justify-between ${selectedCategories.includes(cat.key)
                          ? 'bg-blue-600 dark:bg-blue-500 text-white'
                          : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                          }`}
                        title={`${cat.description}\n\nTimestamp: ${cat.timestamp_meaning}`}
                      >
                        <div className="font-semibold">{cat.name}</div>
                        <div className="text-[10px] opacity-75">
                          {summary[cat.name] ? `${summary[cat.name]} entries` : '\u00A0'}
                        </div>
                      </button>
                    ))}
                </div>
              </div>

              {/* Group By */}
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Group By
                </label>
                <div className="flex gap-2">
                  {(['category', 'none'] as const).map((option) => (
                    <button
                      key={option}
                      onClick={() => setGroupBy(option)}
                      className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${groupBy === option
                        ? 'bg-blue-600 dark:bg-blue-500 text-white'
                        : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                        }`}
                    >
                      {option.charAt(0).toUpperCase() + option.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Summary Stats */}
          {!loading && entries.length > 0 && (
            <div className="mt-3 flex items-center justify-between">
              <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                <span>
                  Total: <strong className="text-gray-900 dark:text-white">{filteredEntries.length}</strong>
                </span>
              </div>
              {totalPages > 1 && (
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  Page {page + 1} of {totalPages}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <div className="flex gap-1">
                  <div
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{ animationDelay: '0ms' }}
                  />
                  <div
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{ animationDelay: '150ms' }}
                  />
                  <div
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{ animationDelay: '300ms' }}
                  />
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Analyzing user activity...
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <p className="text-red-600 dark:text-red-400 mb-2">
                  Error loading user activity
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
                <button
                  onClick={loadUserActivity}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
                >
                  Retry
                </button>
              </div>
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <DocumentTextIcon className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No User Activity Found
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {entries.length === 0
                    ? 'Upload NTUSER.DAT registry hives to begin analysis.'
                    : 'Try adjusting your filters.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col h-full">
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {Object.entries(paginatedGroupedEntries).map(([groupName, groupEntries]) => (
                  <div key={groupName}>
                    {groupBy !== 'none' && (
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 px-2">
                        {groupName} ({groupEntries.length})
                      </h3>
                    )}
                    <div className="space-y-2">
                      {groupEntries.map((entry) => {
                        const globalIndex = filteredEntries.indexOf(entry);
                        const isExpanded = expandedEntries.has(globalIndex);

                        return (
                          <div
                            key={globalIndex}
                            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
                          >
                            {/* Entry Header */}
                            <div
                              className="p-3 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                              onClick={() => toggleEntry(globalIndex)}
                            >
                              <div className="flex items-start gap-3">
                                {/* Category Icon */}
                                <div className="flex-shrink-0 mt-0.5 text-blue-500 dark:text-blue-400">
                                  {getCategoryIcon(entry.category)}
                                </div>

                                {/* Entry Info */}
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                                    <span
                                      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300"
                                      dangerouslySetInnerHTML={{ __html: highlightText(entry.category) }}
                                    />
                                    {entry.user_context && (
                                      <span
                                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300"
                                      >
                                        <UserIcon className="w-3 h-3" />
                                        {entry.user_context}
                                      </span>
                                    )}
                                    {entry.artifact_sequence_id && (
                                      <span
                                        className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300"
                                        title="Artifact Sequence ID (timestamp may not be factual)"
                                      >
                                        Seq #{entry.artifact_sequence_id}
                                      </span>
                                    )}
                                  </div>
                                  <div
                                    className="text-sm text-gray-900 dark:text-white break-all mb-1"
                                    dangerouslySetInnerHTML={{ __html: highlightText(entry.activity_description) }}
                                  />
                                  {entry.timestamp && (
                                    <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-500">
                                      <ClockIcon className="w-3 h-3" />
                                      {formatTimestamp(entry.timestamp)}
                                    </div>
                                  )}
                                </div>

                                {/* Expand Icon */}
                                <div>
                                  {isExpanded ? (
                                    <ChevronUpIcon className="w-5 h-5 text-gray-400" />
                                  ) : (
                                    <ChevronDownIcon className="w-5 h-5 text-gray-400" />
                                  )}
                                </div>
                              </div>
                            </div>

                            {/* Add to Timeline Button */}
                            {entry.event_id && (
                              <div className="px-3 pb-2">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    addToTimeline(entry);
                                  }}
                                  disabled={addingToTimeline === entry.event_id}
                                  className="flex items-center gap-1 px-2 py-1 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 text-white rounded text-xs font-medium transition-colors"
                                  title="Add to timeline"
                                >
                                  {addingToTimeline === entry.event_id ? (
                                    <>
                                      <div className="w-3 h-3 border-2 border-blue-200 dark:border-blue-300 border-t-transparent rounded-full animate-spin" />
                                      Adding...
                                    </>
                                  ) : (
                                    <>
                                      <PlusIcon className="w-3 h-3" />
                                      Add to Timeline
                                    </>
                                  )}
                                </button>
                              </div>
                            )}

                            {/* Expanded Details */}
                            {isExpanded && (
                              <div className="border-t border-gray-200 dark:border-gray-700 p-3 bg-gray-50 dark:bg-gray-900">
                                <div className="space-y-3">
                                  {/* Category Description */}
                                  <div>
                                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                      Artifact Description
                                    </label>
                                    <div className="text-sm text-gray-900 dark:text-white">
                                      {entry.description}
                                    </div>
                                  </div>

                                  {/* Timestamp Meaning */}
                                  <div>
                                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                      Timestamp Meaning
                                    </label>
                                    <div className="text-sm text-gray-900 dark:text-white italic">
                                      {entry.timestamp_meaning}
                                    </div>
                                  </div>

                                  {/* Event ID */}
                                  {entry.event_id && (
                                    <div>
                                      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Event ID
                                      </label>
                                      <div className="text-sm text-gray-900 dark:text-white">
                                        #{entry.event_id}
                                      </div>
                                    </div>
                                  )}

                                  {/* Additional Data */}
                                  {entry.additional_data &&
                                    Object.keys(entry.additional_data).length > 0 && (
                                      <div>
                                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                          Additional Data
                                        </label>
                                        <div className="bg-white dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                                          {Object.entries(entry.additional_data).map(
                                            ([key, value]) => (
                                              <div
                                                key={key}
                                                className="flex gap-2 text-xs py-1"
                                              >
                                                <span className="font-medium text-gray-700 dark:text-gray-300">
                                                  {key}:
                                                </span>
                                                <span className="text-gray-900 dark:text-white font-mono">
                                                  {typeof value === 'object'
                                                    ? JSON.stringify(value)
                                                    : String(value)}
                                                </span>
                                              </div>
                                            )
                                          )}
                                        </div>
                                      </div>
                                    )}

                                  {/* Raw Data */}
                                  {entry.raw_data && Object.keys(entry.raw_data).length > 0 && (
                                    <div>
                                      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Raw Data
                                      </label>
                                      <TypedDictionaryViewer
                                        data={entry.raw_data}
                                        title=""
                                        onAddToTimeline={() => { }}
                                      />
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination Controls */}
              {totalPages > 1 && (
                <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800">
                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Previous
                    </button>
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      Showing {page * pageSize + 1}-
                      {Math.min((page + 1) * pageSize, filteredEntries.length)} of{' '}
                      {filteredEntries.length}
                    </span>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default UserActivityViewer;
