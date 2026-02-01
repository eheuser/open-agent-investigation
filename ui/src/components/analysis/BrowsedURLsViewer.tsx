import React, { useState, useEffect, useCallback } from 'react';
import {
  GlobeAltIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
  TrashIcon,
  FunnelIcon,
  ClockIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import api from '../../services/api';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import TypedDictionaryViewer from '../TypedDictionaryViewer';

interface BrowsedURLEntry {
  browser: string;
  url: string;
  title: string | null;
  visit_count: number | null;
  timestamp: string | null;
  event_id: number | null;
  artifact_sequence_id: number | null;
  additional_data: Record<string, any>;
  raw_data: Record<string, any>;
}

interface BrowserInfo {
  key: string;
  name: string;
  description: string;
  icon: string;
}

interface BrowsedURLsViewerProps {
  investigationId: string;
}

const BrowsedURLsViewer: React.FC<BrowsedURLsViewerProps> = ({ investigationId }) => {
  const [entries, setEntries] = useState<BrowsedURLEntry[]>([]);
  const [filteredEntries, setFilteredEntries] = useState<BrowsedURLEntry[]>([]);
  const [browsers, setBrowsers] = useState<BrowserInfo[]>([]);
  const [selectedBrowsers, setSelectedBrowsers] = useState<string[]>([]);
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set());
  const [page, setPage] = useState(0);
  const [pageSize] = useState(50);
  const [showClearCacheConfirm, setShowClearCacheConfirm] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);

  const { subscribe } = useWebSocketContext();

  const loadBrowsers = useCallback(async () => {
    try {
      const response = await api.get('/api/v1/analysis/browsed-urls/browsers');
      setBrowsers(response.data.browsers);
    } catch (err: any) {
      console.error('Failed to load browsers:', err);
    }
  }, []);

  const loadBrowsedURLs = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params: any = {};
      if (selectedBrowsers.length > 0) {
        params.browsers = selectedBrowsers;
      }

      const response = await api.get(`/api/v1/analysis/browsed-urls/${investigationId}`, { params });
      
      setEntries(response.data.entries);
      setSummary(response.data.summary);
    } catch (err: any) {
      console.error('Failed to load browsed URLs:', err);
      setError(err.response?.data?.detail || 'Failed to load browsed URLs');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [investigationId, selectedBrowsers]);

  const clearCache = async () => {
    setClearingCache(true);
    try {
      await api.delete(`/api/v1/analysis/cache/${investigationId}`);
      setShowClearCacheConfirm(false);
      await loadBrowsedURLs();
    } catch (err: any) {
      console.error('Failed to clear cache:', err);
      setError(err.response?.data?.detail || 'Failed to clear cache');
    } finally {
      setClearingCache(false);
    }
  };

  useEffect(() => {
    loadBrowsers();
  }, [loadBrowsers]);

  useEffect(() => {
    loadBrowsedURLs();
  }, [loadBrowsedURLs]);

  // WebSocket subscription for auto-refresh
  useEffect(() => {
    const handleMessage = (message: any) => {
      if (
        message.type === 'events_inserted' ||
        message.type === 'parsing_complete' ||
        message.type === 'job_status_update'
      ) {
        if (message.investigation_id === investigationId) {
          loadBrowsedURLs();
        }
      }
    };

    const unsubscribe = subscribe(handleMessage);
    return unsubscribe;
  }, [subscribe, investigationId, loadBrowsedURLs]);

  // Apply filters when entries or filter settings change
  useEffect(() => {
    let filtered = [...entries];

    if (searchText) {
      const searchLower = searchText.toLowerCase();
      filtered = filtered.filter(
        (entry) =>
          entry.url?.toLowerCase().includes(searchLower) ||
          entry.title?.toLowerCase().includes(searchLower) ||
          entry.browser?.toLowerCase().includes(searchLower)
      );
    }

    setFilteredEntries(filtered);
    setPage(0);
  }, [entries, searchText]);

  const toggleBrowser = (browserKey: string) => {
    setSelectedBrowsers((prev) => {
      if (prev.includes(browserKey)) {
        return prev.filter((b) => b !== browserKey);
      } else {
        return [...prev, browserKey];
      }
    });
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

  const formatTimestamp = (ts?: string | null) => {
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

  const getBrowserIcon = (browserKey: string) => {
    const icons: Record<string, string> = {
      chrome_chromium: '🌐',
      firefox: '🦊',
      edge_legacy: '🔷',
    };
    return icons[browserKey] || '🌍';
  };

  const getBrowserColor = (browserKey: string) => {
    const colors: Record<string, string> = {
      chrome_chromium: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
      firefox: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
      edge_legacy: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-200',
    };
    return colors[browserKey] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
  };

  // Calculate pagination
  const totalPages = Math.ceil(filteredEntries.length / pageSize);
  const paginatedEntries = filteredEntries.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <>
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
              This will clear all cached browsed URLs results and force a fresh analysis on the next request. Use this if you've uploaded new artifacts and want to see updated results immediately.
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
                Browsed URLs Analysis
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Browser history from Chrome, Firefox, and Edge
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
                onClick={loadBrowsedURLs}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Analyzing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {/* Browser Filters */}
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700 mb-3">
            <div className="flex items-center gap-2 mb-2">
              <FunnelIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300">Filter by Browser</label>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {browsers.map((browser) => (
                <button
                  key={browser.key}
                  onClick={() => toggleBrowser(browser.key)}
                  className={`px-3 py-2 rounded-md text-xs font-medium transition-colors text-left min-h-[4.5rem] flex flex-col justify-between ${
                    selectedBrowsers.includes(browser.key)
                      ? 'bg-blue-600 dark:bg-blue-500 text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-lg">{getBrowserIcon(browser.key)}</span>
                    <div>
                      <div className="font-semibold">{browser.name}</div>
                      <div className="text-[10px] opacity-75 mt-0.5">{browser.description}</div>
                    </div>
                  </div>
                  <div className="text-[10px] opacity-75">
                    {summary[browser.key] ? `${summary[browser.key]} entries` : '\u00A0'}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Search Bar */}
          <div className="relative mb-3">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Search URLs, titles, or browsers..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
            />
          </div>

          {/* Summary Stats */}
          {!loading && entries.length > 0 && (
            <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
              <span>
                Total: <strong className="text-gray-900 dark:text-white">{filteredEntries.length}</strong>
                {searchText && ` (filtered from ${entries.length})`}
              </span>
              {totalPages > 1 && (
                <span>
                  Page {page + 1} of {totalPages}
                </span>
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
                  Analyzing browsed URLs...
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <p className="text-red-600 dark:text-red-400 mb-2">
                  Error loading browsed URLs
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
                <button
                  onClick={loadBrowsedURLs}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
                >
                  Retry
                </button>
              </div>
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <GlobeAltIcon className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No Browsed URLs Found
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {entries.length === 0
                    ? 'Upload browser history artifacts (History, places.sqlite, WebCacheV*.dat) to see results.'
                    : 'Try adjusting your filters or search term.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col h-full">
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {paginatedEntries.map((entry, index) => {
                  const globalIndex = page * pageSize + index;
                  const isExpanded = expandedEntries.has(globalIndex);

                  return (
                    <div
                      key={entry.event_id || globalIndex}
                      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
                    >
                      {/* Entry Header */}
                      <div
                        className="p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
                        onClick={() => toggleEntry(globalIndex)}
                      >
                        <div className="flex items-start gap-3">
                          {/* Browser Icon */}
                          <div className="text-2xl mt-0.5">{getBrowserIcon(entry.browser)}</div>

                          {/* Entry Info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getBrowserColor(
                                  entry.browser
                                )}`}
                              >
                                {entry.browser}
                              </span>
                              {entry.visit_count !== null && entry.visit_count > 1 && (
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                  {entry.visit_count} visits
                                </span>
                              )}
                            </div>
                            <div
                              className="text-sm text-gray-900 dark:text-white font-mono break-all mb-1"
                              dangerouslySetInnerHTML={{ __html: highlightText(entry.url) }}
                            />
                            {entry.title && (
                              <div
                                className="text-sm text-gray-600 dark:text-gray-400 mb-1"
                                dangerouslySetInnerHTML={{ __html: highlightText(entry.title) }}
                              />
                            )}
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

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="border-t border-gray-200 dark:border-gray-700 p-3 bg-gray-50 dark:bg-gray-900">
                          <div className="space-y-3">
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
                            {Object.keys(entry.additional_data).length > 0 && (
                              <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                  Additional Data
                                </label>
                                <div className="bg-white dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                                  {Object.entries(entry.additional_data).map(([key, value]) => (
                                    <div key={key} className="flex gap-2 text-xs py-1">
                                      <span className="font-medium text-gray-700 dark:text-gray-300">
                                        {key}:
                                      </span>
                                      <span className="text-gray-900 dark:text-white font-mono">
                                        {typeof value === 'object'
                                          ? JSON.stringify(value)
                                          : String(value)}
                                      </span>
                                    </div>
                                  ))}
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
                                  onAddToTimeline={() => {}}
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
                      Showing {page * pageSize + 1}-{Math.min((page + 1) * pageSize, filteredEntries.length)} of{' '}
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

export default BrowsedURLsViewer;
