import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import TypedDictionaryViewer from '../TypedDictionaryViewer';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClockIcon,
  UserCircleIcon,
  GlobeAltIcon,
  KeyIcon,
  ShieldExclamationIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  TrashIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';

interface Props {
  investigationId: string;
}

interface LogonEntry {
  logon_type: string;
  event_action: string;
  username: string;
  domain?: string;
  logon_id?: string;
  source_ip?: string;
  source_host?: string;
  timestamp?: string;
  event_id?: number;
  event_record_id?: number;
  logon_process?: string;
  authentication_package?: string;
  failure_reason?: string;
  status_code?: string;
  raw_data?: any;
}

interface LogonsResponse {
  entries: LogonEntry[];
  total: number;
  summary: { [key: string]: number };
}

interface FilterCategory {
  key: string;
  name: string;
  description: string;
  icon: string;
}

interface FilterCategories {
  logon_types: FilterCategory[];
  source_ips: never[];
  usernames: never[];
}

interface DynamicFilters {
  source_ips: string[];
  usernames: string[];
}

const LogonsViewer: React.FC<Props> = ({ investigationId }) => {
  const [entries, setEntries] = useState<LogonEntry[]>([]); // Current entries (may be server-filtered)
  const [filteredEntries, setFilteredEntries] = useState<LogonEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cardinalityCounts, setCardinalityCounts] = useState<{
    logonTypes: Record<string, number>;
    sourceIPs: Record<string, number>;
    usernames: Record<string, number>;
  }>({ logonTypes: {}, sourceIPs: {}, usernames: {} });

  // Pagination
  const [page, setPage] = useState(0);
  const [pageSize] = useState(50);

  // Filters
  const [searchText, setSearchText] = useState('');
  const [selectedLogonTypes, setSelectedLogonTypes] = useState<string[]>([]);
  const [selectedSourceIPs, setSelectedSourceIPs] = useState<string[]>([]);
  const [selectedUsernames, setSelectedUsernames] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(true);

  // Available filter categories
  const [filterCategories, setFilterCategories] = useState<FilterCategories>({
    logon_types: [],
    source_ips: [],
    usernames: [],
  });
  const [dynamicFilters, setDynamicFilters] = useState<DynamicFilters>({
    source_ips: [],
    usernames: [],
  });

  // Summary
  const [summary, setSummary] = useState<{ [key: string]: number }>({});

  // Expanded entries
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set());

  // Clear cache modal
  const [showClearCacheConfirm, setShowClearCacheConfirm] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);

  // Add to timeline
  const [addingToTimeline, setAddingToTimeline] = useState<number | null>(null);
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Active filter category (for UI tabs)
  const [activeFilterTab, setActiveFilterTab] = useState<'logon_types' | 'source_ips' | 'usernames'>('logon_types');

  // Load filter categories and initial data on mount
  useEffect(() => {
    loadFilterCategories();
    loadInitialData(); // Load all data and calculate counts
  }, [investigationId]);

  // Reload filtered data when filters change (but keep cardinality counts from initial load)
  useEffect(() => {
    if (selectedLogonTypes.length > 0 || selectedSourceIPs.length > 0 || selectedUsernames.length > 0) {
      // At least one filter is active - load filtered data from server
      loadLogons();
    } else {
      // No filters active - reload all data from server
      // We need to fetch fresh data, not just apply client-side filters
      // because 'entries' might contain only the previously filtered subset
      loadInitialData();
    }
  }, [selectedLogonTypes, selectedSourceIPs, selectedUsernames]);

  // Subscribe to WebSocket for real-time updates
  const { subscribe } = useWebSocketContext();

  useEffect(() => {
    const handleMessage = (message: any) => {
      // Only refresh when parsing is COMPLETE, not on every event insertion
      // This prevents resource contention during parsing
      if (
        message.type === 'parsing_complete'
      ) {
        if (message.investigation_id === investigationId) {
          loadInitialData(); // Refresh all data and cardinality counts
        }
      }
    };

    const unsubscribe = subscribe(handleMessage);
    return unsubscribe;
  }, [subscribe, investigationId, selectedLogonTypes, selectedSourceIPs, selectedUsernames]);

  // Apply client-side search filter when entries or search text change
  useEffect(() => {
    applyFilters();
    setPage(0);
  }, [entries, searchText]);

  const loadFilterCategories = async () => {
    try {
      const response = await api.get<{ filter_categories: FilterCategories }>(
        '/api/v1/analysis/logons/filter-categories'
      );
      setFilterCategories(response.data.filter_categories);
    } catch (err: any) {
      console.error('Failed to load filter categories:', err);
    }
  };

  // No longer needed - we build dynamic filters from cardinality counts
  // const loadDynamicFilters = async () => {
  //   try {
  //     const response = await api.get<{ dynamic_filters: DynamicFilters }>(
  //       `/api/v1/analysis/logons/dynamic-filters/${investigationId}`
  //     );
  //     setDynamicFilters(response.data.dynamic_filters);
  //   } catch (err: any) {
  //     console.error('Failed to load dynamic filters:', err);
  //   }
  // };

  const loadInitialData = async () => {
    // Load all entries without filters for initial display and cardinality counts
    setLoading(true);
    setError(null);

    try {
      const response = await api.get<LogonsResponse>(
        `/api/v1/analysis/logons/${investigationId}`
      );

      //console.log('Loaded initial data:', response.data.entries.length, 'entries');
      setEntries(response.data.entries);
      setSummary(response.data.summary);

      // Calculate cardinality counts from all entries
      const logonTypeCounts: Record<string, number> = {};
      const sourceIPCounts: Record<string, number> = {};
      const usernameCounts: Record<string, number> = {};

      response.data.entries.forEach(entry => {
        // Count logon types
        logonTypeCounts[entry.logon_type] = (logonTypeCounts[entry.logon_type] || 0) + 1;

        // Count source IPs
        if (entry.source_ip) {
          sourceIPCounts[entry.source_ip] = (sourceIPCounts[entry.source_ip] || 0) + 1;
        }

        // Count usernames
        if (entry.username) {
          usernameCounts[entry.username] = (usernameCounts[entry.username] || 0) + 1;
        }
      });

      setCardinalityCounts({
        logonTypes: logonTypeCounts,
        sourceIPs: sourceIPCounts,
        usernames: usernameCounts,
      });

      //console.log('Cardinality counts:', { logonTypeCounts, sourceIPCounts, usernameCounts });

      // Build dynamic filter lists from the cardinality counts, sorted by count (descending)
      const sourceIPList = Object.keys(sourceIPCounts).sort((a, b) => sourceIPCounts[b] - sourceIPCounts[a]);
      const usernameList = Object.keys(usernameCounts).sort((a, b) => usernameCounts[b] - usernameCounts[a]);

      setDynamicFilters({
        source_ips: sourceIPList,
        usernames: usernameList,
      });

      //console.log('Dynamic filters set:', { sourceIPList: sourceIPList.length, usernameList: usernameList.length });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load logon data');
      console.error('Failed to load initial data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadLogons = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();

      // Add logon type filters
      if (selectedLogonTypes.length > 0) {
        selectedLogonTypes.forEach((type) => {
          params.append('logon_types', type);
        });
      }

      // Add source IP filters
      if (selectedSourceIPs.length > 0) {
        selectedSourceIPs.forEach((ip) => {
          params.append('source_ips', ip);
        });
      }

      // Add username filters
      if (selectedUsernames.length > 0) {
        selectedUsernames.forEach((username) => {
          params.append('usernames', username);
        });
      }

      //console.log('[loadLogons] Requesting filtered data with params:', params.toString());

      const response = await api.get<LogonsResponse>(
        `/api/v1/analysis/logons/${investigationId}?${params.toString()}`
      );

      //console.log('[loadLogons] Received', response.data.entries.length, 'entries from server');
      //console.log('[loadLogons] Current entries.length before setEntries:', entries.length);

      // Set entries (this will trigger applyFilters via useEffect)
      setEntries(response.data.entries);
      setSummary(response.data.summary);

      //console.log('[loadLogons] Called setEntries with', response.data.entries.length, 'entries');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load logon data');
      console.error('Failed to load logons:', err);
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    //console.log('[applyFilters] Called with entries.length:', entries.length, 'searchText:', searchText);
    let filtered = [...entries];

    // Only apply client-side search text filtering
    // Server-side filters (logon types, source IPs, usernames) are already applied in 'entries'
    if (searchText) {
      const searchLower = searchText.toLowerCase();
      filtered = filtered.filter(
        (entry) =>
          entry.username.toLowerCase().includes(searchLower) ||
          (entry.domain && entry.domain.toLowerCase().includes(searchLower)) ||
          (entry.source_ip && entry.source_ip.toLowerCase().includes(searchLower)) ||
          (entry.source_host && entry.source_host.toLowerCase().includes(searchLower)) ||
          entry.logon_type.toLowerCase().includes(searchLower) ||
          entry.event_action.toLowerCase().includes(searchLower)
      );
    }

    //console.log('[applyFilters] Setting filteredEntries to', filtered.length, 'entries');
    setFilteredEntries(filtered);
  };

  const toggleLogonType = (type: string) => {
    setSelectedLogonTypes((prev) => {
      const isSelected = prev.includes(type);
      if (isSelected) {
        // Remove the type
        return prev.filter((t) => t !== type);
      } else {
        // Add the type
        return [...prev, type];
      }
    });
  };

  const toggleSourceIP = (ip: string) => {
    setSelectedSourceIPs((prev) => {
      const isSelected = prev.includes(ip);
      if (isSelected) {
        // Remove the IP
        return prev.filter((i) => i !== ip);
      } else {
        // Add the IP
        return [...prev, ip];
      }
    });
  };

  const toggleUsername = (username: string) => {
    setSelectedUsernames((prev) => {
      const isSelected = prev.includes(username);
      if (isSelected) {
        // Remove the username
        return prev.filter((u) => u !== username);
      } else {
        // Add the username
        return [...prev, username];
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

  const formatTimestamp = (ts?: string) => {
    if (!ts) return 'N/A';
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  const getEventActionColor = (action: string) => {
    if (action.includes('Failed')) {
      return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
    } else if (action.includes('Logoff')) {
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    } else {
      return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200';
    }
  };

  const getEventActionIcon = (action: string) => {
    if (action.includes('Failed')) {
      return <XCircleIcon className="w-5 h-5 text-red-500 dark:text-red-400" />;
    } else if (action.includes('Logoff')) {
      return <ShieldExclamationIcon className="w-5 h-5 text-gray-500 dark:text-gray-400" />;
    } else {
      return <CheckCircleIcon className="w-5 h-5 text-green-500 dark:text-green-400" />;
    }
  };

  const getLogonTypeIcon = (type: string) => {
    const iconMap: Record<string, React.ReactElement> = {
      Interactive: <UserCircleIcon className="w-4 h-4" />,
      Network: <GlobeAltIcon className="w-4 h-4" />,
      RemoteInteractive: <GlobeAltIcon className="w-4 h-4" />,
      Service: <KeyIcon className="w-4 h-4" />,
    };
    return iconMap[type] || <UserCircleIcon className="w-4 h-4" />;
  };

  // Get cardinality counts from pre-calculated counts
  const getLogonTypeCount = (type: string) => {
    return cardinalityCounts.logonTypes[type] || 0;
  };

  const getSourceIPCount = (ip: string) => {
    return cardinalityCounts.sourceIPs[ip] || 0;
  };

  const getUsernameCount = (username: string) => {
    return cardinalityCounts.usernames[username] || 0;
  };

  // Calculate pagination
  const totalPages = Math.ceil(filteredEntries.length / pageSize);
  const paginatedEntries = filteredEntries.slice(page * pageSize, (page + 1) * pageSize);

  const clearCache = async () => {
    setClearingCache(true);
    try {
      await api.delete(`/api/v1/analysis/cache/${investigationId}`);
      setShowClearCacheConfirm(false);
      // Clear all filters and reload initial data
      setSelectedLogonTypes([]);
      setSelectedSourceIPs([]);
      setSelectedUsernames([]);
      await loadInitialData();
    } catch (err: any) {
      console.error('Failed to clear cache:', err);
      setError(err.response?.data?.detail || 'Failed to clear cache');
    } finally {
      setClearingCache(false);
    }
  };

  const addToTimeline = async (entry: LogonEntry) => {
    if (!entry.event_id) {
      //console.warn('Cannot add to timeline: entry has no event_id');
      return;
    }

    setAddingToTimeline(entry.event_id);
    try {
      await api.post(`/api/v1/timeline/${investigationId}/entries`, {
        event_id: entry.event_id,
        timestamp: entry.timestamp || new Date().toISOString(),
        entry_type: 'event',
        title: `${entry.event_action}: ${entry.username}`,
        description: `Logon Type: ${entry.logon_type}${entry.source_ip ? '\nSource IP: ' + entry.source_ip : ''}${entry.source_host ? '\nSource Host: ' + entry.source_host : ''}`,
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
              This will clear all cached logon results and force a fresh analysis on the next
              request. Use this if you've uploaded new artifacts and want to see updated results
              immediately.
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
                Logons Analysis
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Logon, logoff, and failed logon events
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
                onClick={loadLogons}
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
                placeholder="Search username, domain, IP address..."
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
              {/* Filter Category Tabs */}
              <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700 pb-2">
                <button
                  onClick={() => setActiveFilterTab('logon_types')}
                  className={`px-3 py-1.5 rounded-t-md text-xs font-medium transition-colors ${activeFilterTab === 'logon_types'
                      ? 'bg-blue-600 dark:bg-blue-500 text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                >
                  Logon Types
                </button>
                <button
                  onClick={() => setActiveFilterTab('source_ips')}
                  className={`px-3 py-1.5 rounded-t-md text-xs font-medium transition-colors ${activeFilterTab === 'source_ips'
                      ? 'bg-blue-600 dark:bg-blue-500 text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                >
                  Source IPs ({dynamicFilters.source_ips.length})
                </button>
                <button
                  onClick={() => setActiveFilterTab('usernames')}
                  className={`px-3 py-1.5 rounded-t-md text-xs font-medium transition-colors ${activeFilterTab === 'usernames'
                      ? 'bg-blue-600 dark:bg-blue-500 text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                >
                  Usernames ({dynamicFilters.usernames.length})
                </button>
              </div>

              {/* Logon Types Filter */}
              {activeFilterTab === 'logon_types' && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Filter by Logon Type
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {filterCategories.logon_types
                      .sort((a, b) => getLogonTypeCount(b.key) - getLogonTypeCount(a.key))
                      .map((type) => {
                        const count = getLogonTypeCount(type.key);
                        return (
                          <button
                            key={type.key}
                            onClick={() => toggleLogonType(type.key)}
                            className={`px-3 py-2 rounded-md text-xs font-medium transition-colors text-left min-h-[4.5rem] flex flex-col justify-between ${selectedLogonTypes.includes(type.key)
                                ? 'bg-blue-600 dark:bg-blue-500 text-white'
                                : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                              }`}
                            title={type.description}
                          >
                            <div>
                              <div className="font-semibold">{type.name}</div>
                              <div className="text-[10px] opacity-75 mt-0.5">{type.description}</div>
                            </div>
                            <div className="text-[10px] opacity-75">
                              {count > 0 ? `${count} ${count === 1 ? 'event' : 'events'}` : '\u00A0'}
                            </div>
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Source IPs Filter */}
              {activeFilterTab === 'source_ips' && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Filter by Source IP Address
                  </label>
                  {dynamicFilters.source_ips.length === 0 ? (
                    <p className="text-xs text-gray-500 dark:text-gray-400 italic">
                      No source IP addresses found in the data.
                    </p>
                  ) : (
                    <div className="grid grid-cols-3 gap-2 max-h-64 overflow-y-auto">
                      {dynamicFilters.source_ips.map((ip) => {
                        const count = getSourceIPCount(ip);
                        return (
                          <button
                            key={ip}
                            onClick={() => toggleSourceIP(ip)}
                            className={`px-3 py-2 rounded-md text-xs font-medium transition-colors text-left min-h-[3.5rem] flex flex-col justify-between ${selectedSourceIPs.includes(ip)
                                ? 'bg-blue-600 dark:bg-blue-500 text-white'
                                : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                              }`}
                          >
                            <div className="font-mono break-all">{ip}</div>
                            <div className="text-[10px] opacity-75 mt-1">
                              {count} {count === 1 ? 'event' : 'events'}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Usernames Filter */}
              {activeFilterTab === 'usernames' && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Filter by Username
                  </label>
                  {dynamicFilters.usernames.length === 0 ? (
                    <p className="text-xs text-gray-500 dark:text-gray-400 italic">
                      No usernames found in the data.
                    </p>
                  ) : (
                    <div className="grid grid-cols-3 gap-2 max-h-64 overflow-y-auto">
                      {dynamicFilters.usernames.map((username) => {
                        const count = getUsernameCount(username);
                        return (
                          <button
                            key={username}
                            onClick={() => toggleUsername(username)}
                            className={`px-3 py-2 rounded-md text-xs font-medium transition-colors text-left min-h-[3.5rem] flex flex-col justify-between ${selectedUsernames.includes(username)
                                ? 'bg-blue-600 dark:bg-blue-500 text-white'
                                : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                              }`}
                          >
                            <div className="font-semibold break-all">{username}</div>
                            <div className="text-[10px] opacity-75 mt-1">
                              {count} {count === 1 ? 'event' : 'events'}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Summary Stats */}
          {!loading && entries.length > 0 && (
            <div className="mt-3 flex items-center justify-between">
              <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                <span>
                  Total: <strong className="text-gray-900 dark:text-white">{filteredEntries.length}</strong>
                </span>
                <span>
                  Logons:{' '}
                  <strong className="text-green-600 dark:text-green-400">
                    {summary['action_Logon'] || 0}
                  </strong>
                </span>
                <span>
                  Failed:{' '}
                  <strong className="text-red-600 dark:text-red-400">
                    {summary['action_Failed Logon'] || 0}
                  </strong>
                </span>
                <span>
                  Logoffs:{' '}
                  <strong className="text-gray-600 dark:text-gray-400">
                    {(summary['action_Logoff'] || 0) + (summary['action_User Initiated Logoff'] || 0)}
                  </strong>
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
                <p className="text-sm text-gray-500 dark:text-gray-400">Analyzing logon events...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <p className="text-red-600 dark:text-red-400 mb-2">Error loading logon events</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
                <button
                  onClick={loadLogons}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
                >
                  Retry
                </button>
              </div>
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <UserCircleIcon className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No Logon Events Found
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {entries.length === 0
                    ? 'Upload Windows Event Log artifacts (Security.evtx) to see logon events.'
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
                        className="p-3 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                        onClick={() => toggleEntry(globalIndex)}
                      >
                        <div className="flex items-start gap-3">
                          {/* Status Icon */}
                          <div className="mt-0.5">{getEventActionIcon(entry.event_action)}</div>

                          {/* Entry Info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getEventActionColor(
                                  entry.event_action
                                )}`}
                              >
                                {entry.event_action}
                              </span>
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                                {getLogonTypeIcon(entry.logon_type)}
                                {entry.logon_type}
                              </span>
                              {entry.source_ip && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300">
                                  <GlobeAltIcon className="w-3 h-3" />
                                  {entry.source_ip}
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-gray-900 dark:text-white font-medium">
                              {entry.domain ? `${entry.domain}\\${entry.username}` : entry.username}
                            </div>
                            {entry.source_host && (
                              <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                From: {entry.source_host}
                              </div>
                            )}
                            {entry.failure_reason && (
                              <div className="text-xs text-red-600 dark:text-red-400 mt-1">
                                Reason: {entry.failure_reason}
                              </div>
                            )}
                            {entry.timestamp && (
                              <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-500 mt-1">
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
                      </div>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="border-t border-gray-200 dark:border-gray-700 p-3 bg-gray-50 dark:bg-gray-900">
                          <div className="grid grid-cols-2 gap-3 mb-3">
                            {entry.logon_id && (
                              <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                  Logon ID
                                </label>
                                <div className="text-sm text-gray-900 dark:text-white font-mono">
                                  {entry.logon_id}
                                </div>
                              </div>
                            )}
                            {entry.event_record_id && (
                              <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                  Event Record ID
                                </label>
                                <div className="text-sm text-gray-900 dark:text-white">
                                  {entry.event_record_id}
                                </div>
                              </div>
                            )}
                            {entry.logon_process && (
                              <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                  Logon Process
                                </label>
                                <div className="text-sm text-gray-900 dark:text-white">
                                  {entry.logon_process}
                                </div>
                              </div>
                            )}
                            {entry.authentication_package && (
                              <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                  Authentication Package
                                </label>
                                <div className="text-sm text-gray-900 dark:text-white">
                                  {entry.authentication_package}
                                </div>
                              </div>
                            )}
                            {entry.status_code && (
                              <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                  Status Code
                                </label>
                                <div className="text-sm text-gray-900 dark:text-white font-mono">
                                  {entry.status_code}
                                </div>
                              </div>
                            )}
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
                          </div>

                          {entry.raw_data && Object.keys(entry.raw_data).length > 0 && (
                            <div>
                              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Raw Event Data
                              </label>
                              <TypedDictionaryViewer
                                data={entry.raw_data}
                                title=""
                                onAddToTimeline={() => { }}
                              />
                            </div>
                          )}
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

export default LogonsViewer;
