import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import TypedDictionaryViewer from './TypedDictionaryViewer';
import { 
  MagnifyingGlassIcon, 
  CalendarIcon,
  XMarkIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  LightBulbIcon,
  PlusIcon,
  TrashIcon
} from '@heroicons/react/24/outline';

interface TimelineEntry {
  entry_id: number;
  investigation_id: string;
  event_id: number | null;
  timestamp: string;
  entry_type: 'event' | 'finding' | 'note' | 'observation';
  title: string;
  description: string | null;
  data: Record<string, any>;
  tags: string[];
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
  is_visible: boolean;
  notes: TimelineNote[];
}

interface TimelineNote {
  note_id: number;
  entry_id: number;
  user_id: number;
  note_text: string;
  created_at: string;
  updated_at: string;
  username: string | null;
}

interface TimelineViewerProps {
  investigationId: string;
}

interface JsonbQuery {
  id: string;
  path: string;
  operator: string;
  value: string;
}

const TimelineViewer: React.FC<TimelineViewerProps> = ({ investigationId }) => {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set());
  const [deletingEntry, setDeletingEntry] = useState<number | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [entryToDelete, setEntryToDelete] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  
  // Pagination
  const [page, setPage] = useState(0);
  const [limit] = useState(50);
  const [total, setTotal] = useState(0);
  
  // Date range filters
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  
  // Sort order (always by time, but can be ascending or descending)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  
  // JSONB Query Filters (for data field queries)
  const [jsonbPath, setJsonbPath] = useState('');
  const [jsonbOperator, setJsonbOperator] = useState('=');
  const [jsonbValue, setJsonbValue] = useState('');
  const [jsonbQueries, setJsonbQueries] = useState<JsonbQuery[]>([]);
  
  // Field autocomplete
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [autocompleteIndex, setAutocompleteIndex] = useState(0);
  const [commonFields, setCommonFields] = useState<string[]>([]);
  const [showFieldSuggestions, setShowFieldSuggestions] = useState(false);
  
  // Event type filtering
  const [availableEventTypes, setAvailableEventTypes] = useState<Array<{event_type: string, count: number}>>([]);
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [showEventTypeDropdown, setShowEventTypeDropdown] = useState(false);

  // Fetch timeline entries
  const fetchTimeline = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const token = localStorage.getItem('token');
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: (page * limit).toString(),
        order: sortOrder
      });
      
      if (selectedType) params.append('entry_type', selectedType);
      if (eventTypeFilter) params.append('event_type', eventTypeFilter);
      if (selectedTags.length > 0) params.append('tags', selectedTags.join(','));
      if (searchQuery) params.append('search', searchQuery);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      
      // Add JSONB query parameters from breadcrumbs
      jsonbQueries.forEach((query, index) => {
        params.append(`jsonb_path_${index}`, query.path);
        params.append(`jsonb_operator_${index}`, query.operator);
        if (query.value) {
          params.append(`jsonb_value_${index}`, query.value);
        }
      });

      const response = await axios.get(
        `/api/v1/timeline/${investigationId}?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      setEntries(response.data.entries || []);
      setTotal(response.data.total || 0);
      
      // Note: commonFields are now fetched via the dedicated /fields endpoint
      // This ensures we get all available fields, not just from the current page
    } catch (err: any) {
      console.error('Failed to fetch timeline:', err);
      setError(err.response?.data?.detail || 'Failed to load timeline');
    } finally {
      setLoading(false);
    }
  }, [investigationId, page, limit, selectedType, eventTypeFilter, selectedTags, searchQuery, startDate, endDate, sortOrder, jsonbQueries]);
  
  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);
  
  // Fetch available event types on mount
  useEffect(() => {
    const fetchEventTypes = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await axios.get(
          `/api/v1/timeline/${investigationId}/event-types`,
          {
            headers: { Authorization: `Bearer ${token}` }
          }
        );
        
        if (response.data.event_types && response.data.event_types.length > 0) {
          setAvailableEventTypes(response.data.event_types);
          //console.log(`Loaded ${response.data.total_types} event types from timeline`);
        }
      } catch (err) {
        console.error('Failed to fetch event types:', err);
      }
    };
    
    fetchEventTypes();
  }, [investigationId]);
  
  // Fetch available fields (updates when event type filter changes)
  useEffect(() => {
    const fetchAvailableFields = async () => {
      try {
        const token = localStorage.getItem('token');
        // Build URL with optional event_type parameter
        let url = `/api/v1/timeline/${investigationId}/fields`;
        if (eventTypeFilter) {
          url += `?event_type=${encodeURIComponent(eventTypeFilter)}`;
        }
        
        const response = await axios.get<{ fields: string[]; count: number; entries_sampled: number }>(
          url,
          {
            headers: { Authorization: `Bearer ${token}` }
          }
        );
        
        //console.log('Timeline fields API response:', response.data);
        if (response.data && response.data.fields) {
          setCommonFields(response.data.fields);
          //console.log(`Loaded ${response.data.fields.length} fields from ${response.data.entries_sampled} timeline entries`);
        } else {
          //console.warn('No fields returned from API');
          setCommonFields([]);
        }
      } catch (err: any) {
        console.error('Failed to fetch available fields:', err);
        console.error('Error details:', err.response?.data);
        setCommonFields([]);
      }
    };
    
    fetchAvailableFields();
  }, [investigationId, eventTypeFilter]); // Re-fetch when event type filter changes

  const toggleExpanded = (entryId: number) => {
    const newExpanded = new Set(expandedEntries);
    if (newExpanded.has(entryId)) {
      newExpanded.delete(entryId);
    } else {
      newExpanded.add(entryId);
    }
    setExpandedEntries(newExpanded);
  };
  
  const handleSearch = () => {
    setPage(0); // Reset to first page
    fetchTimeline();
  };
  
  const clearFilters = () => {
    setSearchQuery('');
    setEventTypeFilter('');
    setStartDate('');
    setEndDate('');
    setSelectedType(null);
    setSelectedTags([]);
    setJsonbPath('');
    setJsonbOperator('=');
    setJsonbValue('');
    setJsonbQueries([]);
    setPage(0);
  };
  
  const addJsonbQuery = () => {
    if (!jsonbPath.trim()) {
      return;
    }
    
    const newQuery: JsonbQuery = {
      id: `${Date.now()}-${Math.random()}`,
      path: jsonbPath,
      operator: jsonbOperator,
      value: jsonbValue
    };
    
    setJsonbQueries(prev => [...prev, newQuery]);
    
    // Clear the input fields
    setJsonbPath('');
    setJsonbOperator('=');
    setJsonbValue('');
    setPage(0);
  };
  
  const removeJsonbQuery = (id: string) => {
    setJsonbQueries(prev => prev.filter(q => q.id !== id));
    setPage(0);
  };
  
  const clearAllJsonbQueries = () => {
    setJsonbQueries([]);
    setPage(0);
  };
  
  const toggleSortOrder = () => {
    setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc');
    setPage(0);
  };
  
  const formatOperatorDisplay = (operator: string) => {
    const operatorMap: { [key: string]: string } = {
      '=': '=',
      '!=': '≠',
      '>': '>',
      '<': '<',
      '>=': '≥',
      '<=': '≤',
      'LIKE': '~',
      'ILIKE': '~*',
      'CONTAINS': '⊃',
      'STARTS_WITH': '⇒',
      'ENDS_WITH': '⇐'
    };
    return operatorMap[operator] || operator;
  };
  
  const getFilteredFields = () => {
    if (!jsonbPath) return commonFields;
    const searchTerm = jsonbPath.toLowerCase();
    return commonFields.filter(field => 
      field.toLowerCase().includes(searchTerm)
    );
  };
  
  const filteredFields = getFilteredFields();
  
  const handleJsonbPathChange = (value: string) => {
    setJsonbPath(value);
    setShowAutocomplete(value.length > 0 && commonFields.length > 0);
    setAutocompleteIndex(0);
  };
  
  const handleJsonbPathKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showAutocomplete || filteredFields.length === 0) {
      if (e.key === 'Enter') {
        addJsonbQuery();
      }
      return;
    }
    
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setAutocompleteIndex(prev => 
          prev < filteredFields.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setAutocompleteIndex(prev => prev > 0 ? prev - 1 : 0);
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredFields[autocompleteIndex]) {
          setJsonbPath(filteredFields[autocompleteIndex]);
          setShowAutocomplete(false);
        }
        break;
      case 'Escape':
        setShowAutocomplete(false);
        break;
    }
  };
  
  const selectField = (field: string) => {
    setJsonbPath(field);
    setShowAutocomplete(false);
  };
  
  const confirmDelete = (entryId: number) => {
    setEntryToDelete(entryId);
    setShowDeleteConfirm(true);
    setDeleteError(null);
  };
  
  const removeFromTimeline = async () => {
    if (!entryToDelete) return;
    
    const entryId = entryToDelete;
    setDeletingEntry(entryId);
    setDeleteError(null);
    
    try {
      const token = localStorage.getItem('token');
      await axios.delete(
        `/api/v1/timeline/${investigationId}/entries/${entryId}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      
      // Remove from local state
      setEntries(prev => prev.filter(e => e.entry_id !== entryId));
      setTotal(prev => Math.max(0, prev - 1));
      
      // Close modal
      setShowDeleteConfirm(false);
      setEntryToDelete(null);
    } catch (err: any) {
      console.error('Failed to remove timeline entry:', err);
      setDeleteError(err.response?.data?.detail || err.message || 'Failed to remove entry');
    } finally {
      setDeletingEntry(null);
    }
  };
  
  // Helper function to highlight matching text
  const highlightText = (text: string, searchTerms: string[]) => {
    if (!searchTerms.length || !text) return text;
    
    let highlightedText = text;
    searchTerms.forEach(term => {
      if (!term) return;
      const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
      highlightedText = highlightedText.replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-700">$1</mark>');
    });
    
    return highlightedText;
  };
  
  // Build search terms for highlighting
  const getSearchTerms = (): string[] => {
    const terms: string[] = [];
    // Only highlight the search input text, not JSONB queries or event type filters
    if (searchQuery) terms.push(searchQuery);
    return terms;
  };
  
  const searchTerms = getSearchTerms();
  const totalPages = Math.ceil(total / limit);
  const hasActiveFilters = searchQuery || eventTypeFilter || startDate || endDate || selectedType || jsonbQueries.length > 0;

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const getEntryTypeColor = (type: string) => {
    switch (type) {
      case 'event':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
      case 'finding':
        return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
      case 'observation':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      case 'note':
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
    }
  };

  const getEntryTypeIcon = (type: string) => {
    switch (type) {
      case 'event':
        return '📊';
      case 'finding':
        return '🔍';
      case 'observation':
        return '👁️';
      case 'note':
        return '📝';
      default:
        return '•';
    }
  };

  return (
    <>
      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div 
            className="absolute inset-0"
            onClick={() => {
              if (deletingEntry === null) {
                setShowDeleteConfirm(false);
                setEntryToDelete(null);
                setDeleteError(null);
              }
            }}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Remove Timeline Entry
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to remove this entry from the timeline? This action cannot be undone.
            </p>
            
            {deleteError && (
              <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-sm text-red-600 dark:text-red-400">{deleteError}</p>
              </div>
            )}
            
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setEntryToDelete(null);
                  setDeleteError(null);
                }}
                disabled={deletingEntry !== null}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={removeFromTimeline}
                disabled={deletingEntry !== null}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600 rounded-lg disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {deletingEntry !== null ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Removing...
                  </>
                ) : (
                  'Remove'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      
    <div className="flex h-full bg-white dark:bg-gray-900">
      {/* Left Column - Timeline Entries */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          {/* JSONB Query Breadcrumbs */}
          {jsonbQueries.length > 0 && (
          <div className="mx-4 mt-4 mb-3 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-blue-900 dark:text-blue-300">
                Active JSONB Filters:
              </span>
              <button
                onClick={clearAllJsonbQueries}
                className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 font-medium"
              >
                Clear All
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {jsonbQueries.map((query) => (
                <div
                  key={query.id}
                  className="inline-flex items-center gap-1.5 px-2 py-1 bg-white dark:bg-gray-800 border border-blue-300 dark:border-blue-700 rounded-md text-xs font-mono group hover:border-red-400 dark:hover:border-red-600 transition-colors"
                >
                  <span className="text-blue-700 dark:text-blue-300 font-semibold">{query.path}</span>
                  <span className="text-gray-500 dark:text-gray-400">{formatOperatorDisplay(query.operator)}</span>
                  {query.value && (
                    <span className="text-green-700 dark:text-green-300">"{query.value}"</span>
                  )}
                  <button
                    onClick={() => removeJsonbQuery(query.id)}
                    className="ml-1 p-0.5 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
                    title="Remove filter"
                  >
                    <XMarkIcon className="w-3 h-3 text-gray-500 dark:text-gray-400 group-hover:text-red-600 dark:group-hover:text-red-400" />
                  </button>
                </div>
              ))}
            </div>
            </div>
          )}

          {/* Top Row: Total Count, Sort, and Search */}
          <div className="px-4 pt-4 pb-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {hasActiveFilters ? (
                    <>
                      {total.toLocaleString()} filtered
                      <span className="text-xs ml-1">(of all entries)</span>
                    </>
                  ) : (
                    <>{total.toLocaleString()} total</>
                  )}
                </span>
                <button
                  onClick={toggleSortOrder}
                  className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 transition-colors"
                  title={sortOrder === 'desc' ? 'Sort oldest first' : 'Sort newest first'}
                >
                  {sortOrder === 'desc' ? (
                    <ArrowDownIcon className="w-5 h-5" />
                  ) : (
                    <ArrowUpIcon className="w-5 h-5" />
                  )}
                </button>
              </div>
            </div>

            {/* Search Bar */}
            <div className="flex gap-2">
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search title or description..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
            />
          </div>
          <button
            onClick={handleSearch}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Search
          </button>
            </div>
          </div>
        </div>

        {/* Timeline Entries List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Loading timeline...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <p className="text-red-600 dark:text-red-400 mb-2">Error loading timeline</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
                <button
                  onClick={fetchTimeline}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
                >
                  Retry
                </button>
              </div>
            </div>
          ) : entries.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <p className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No Timeline Entries Found
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {hasActiveFilters
                    ? 'Try adjusting your filters or search criteria.'
                    : 'Timeline entries will appear here as the agent investigates'}
                </p>
              </div>
            </div>
          ) : (
            <div className="p-4 space-y-4">
          {entries.map((entry) => (
            <div
              key={entry.entry_id}
              className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden"
            >
              {/* Entry Header - Clickable */}
              <div
                className="p-4 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                onClick={() => toggleExpanded(entry.entry_id)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-2xl">{getEntryTypeIcon(entry.entry_type)}</span>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${getEntryTypeColor(entry.entry_type)}`}>
                        {entry.entry_type}
                      </span>
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        {formatTimestamp(entry.timestamp)}
                      </span>
                    </div>
                    <h3 
                      className="text-lg font-semibold text-gray-900 dark:text-gray-100"
                      dangerouslySetInnerHTML={{ __html: highlightText(entry.title, searchTerms) }}
                    />
                    {entry.description && (
                      <p 
                        className="mt-1 text-gray-600 dark:text-gray-300 line-clamp-2"
                        dangerouslySetInnerHTML={{ __html: highlightText(entry.description, searchTerms) }}
                      />
                    )}
                    {entry.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {entry.tags.map((tag, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-1 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded"
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                    {expandedEntries.has(entry.entry_id) ? '▼' : '▶'}
                  </button>
                </div>
              </div>

              {/* Expanded Details */}
              {expandedEntries.has(entry.entry_id) && (
                <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-900">
                  {/* Remove Button - Top Right */}
                  <div className="flex justify-end mb-4">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        confirmDelete(entry.entry_id);
                      }}
                      disabled={deletingEntry === entry.entry_id}
                      className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 text-white rounded text-sm font-medium transition-colors"
                      title="Remove from timeline"
                    >
                      <TrashIcon className="w-4 h-4" />
                      Remove
                    </button>
                  </div>
                  {/* Full Description */}
                  {entry.description && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                        Description
                      </h4>
                      <p className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                        {entry.description}
                      </p>
                    </div>
                  )}

                  {/* Event Link */}
                  {entry.event_id && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                        Source Event
                      </h4>
                      <p className="text-blue-600 dark:text-blue-400">
                        Event ID: {entry.event_id}
                      </p>
                    </div>
                  )}

                  {/* Event Data (Full Payload) */}
                  {entry.event_id && entry.data.event_payload && (
                    <div className="mb-4">
                      <TypedDictionaryViewer
                        data={entry.data.event_payload}
                        title={`Event Data (Event ID: ${entry.event_id})`}
                        onAddToTimeline={(key, value) => {
                          // Could implement adding specific fields to timeline
                          //console.log('Add to timeline:', key, value);
                        }}
                      />
                    </div>
                  )}

                  {/* Additional Data (Timeline Entry Data - excluding event_payload) */}
                  {(() => {
                    const { event_payload, ...otherData } = entry.data;
                    return Object.keys(otherData).length > 0 && (
                      <div className="mb-4">
                        <TypedDictionaryViewer
                          data={otherData}
                          title="Timeline Entry Data"
                        />
                      </div>
                    );
                  })()}

                  {/* Notes */}
                  {entry.notes && entry.notes.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Notes ({entry.notes.length})
                      </h4>
                      <div className="space-y-2">
                        {entry.notes.map((note) => (
                          <div
                            key={note.note_id}
                            className="bg-white dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700"
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                {note.username || 'Unknown'} • {formatTimestamp(note.created_at)}
                              </span>
                            </div>
                            <p className="text-sm text-gray-700 dark:text-gray-300">
                              {note.note_text}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    Created: {formatTimestamp(entry.created_at)}
                    {entry.updated_at !== entry.created_at && (
                      <> • Updated: {formatTimestamp(entry.updated_at)}</>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {!loading && entries.length > 0 && (
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Showing {page * limit + 1}-{Math.min((page + 1) * limit, total)} of {total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-2 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeftIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                </button>
                <span className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="p-2 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRightIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Right Column - Advanced Search Builder */}
      <div className="w-1/3 min-w-[400px] border-l border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50 dark:bg-gray-800">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
            Advanced Query Builder
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Build complex queries with multiple filters
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Entry Type Filter */}
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
              Entry Type
            </label>
            <select
              value={selectedType || ''}
              onChange={(e) => { setSelectedType(e.target.value || null); setPage(0); }}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
            >
              <option value="">All Types</option>
              <option value="event">Events</option>
              <option value="finding">Findings</option>
              <option value="observation">Observations</option>
              <option value="note">Notes</option>
            </select>
          </div>
          
          {/* Event Type Filter */}
          <div>
            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Event Type Filter
            </h4>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Filter by the event type of linked events
            </p>
            
            <div className="relative">
              <input
                type="text"
                value={eventTypeFilter}
                onChange={(e) => setEventTypeFilter(e.target.value)}
                onFocus={() => setShowEventTypeDropdown(true)}
                onBlur={() => setTimeout(() => setShowEventTypeDropdown(false), 200)}
                placeholder="Select or type event type..."
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm font-mono"
              />
              
              {/* Event Type Dropdown */}
              {showEventTypeDropdown && availableEventTypes.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                  {availableEventTypes
                    .filter(et => !eventTypeFilter || et.event_type.toLowerCase().includes(eventTypeFilter.toLowerCase()))
                    .map((et) => (
                      <button
                        key={et.event_type}
                        onClick={() => {
                          setEventTypeFilter(et.event_type);
                          setShowEventTypeDropdown(false);
                          setPage(0);
                        }}
                        className="w-full text-left px-3 py-2 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors flex items-center justify-between"
                      >
                        <span className="text-sm font-mono text-gray-700 dark:text-gray-300">
                          {et.event_type}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {et.count.toLocaleString()}
                        </span>
                      </button>
                    ))}
                </div>
              )}
            </div>
            
            {eventTypeFilter && (
              <button
                onClick={() => {
                  setEventTypeFilter('');
                  setPage(0);
                }}
                className="mt-2 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200"
              >
                Clear event type filter
              </button>
            )}
          </div>

          {/* JSONB Query Section */}
          <div>
            <div>
              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Data Field Query
              </h4>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                Query specific fields within timeline entry data
              </p>
              
              <div className="space-y-2">
                {/* JSONB Path */}
                <div className="relative">
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Field Path {commonFields.length > 0 && `(${commonFields.length} available)`}
                    </label>
                    {commonFields.length > 0 && (
                      <button
                        onClick={() => setShowFieldSuggestions(!showFieldSuggestions)}
                        className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                      >
                        <LightBulbIcon className="w-3 h-3" />
                        {showFieldSuggestions ? 'Hide' : 'Show'} all fields
                      </button>
                    )}
                  </div>
                  <input
                    type="text"
                    value={jsonbPath}
                    onChange={(e) => handleJsonbPathChange(e.target.value)}
                    onKeyDown={handleJsonbPathKeyDown}
                    onFocus={() => jsonbPath && setShowAutocomplete(true)}
                    onBlur={() => setTimeout(() => setShowAutocomplete(false), 200)}
                    placeholder="Start typing to see suggestions..."
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm font-mono"
                    autoComplete="off"
                  />
                  
                  {/* Autocomplete Dropdown */}
                  {showAutocomplete && filteredFields.length > 0 && (
                    <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                      {filteredFields.map((field, index) => (
                        <button
                          key={field}
                          onClick={() => selectField(field)}
                          className={`w-full text-left px-3 py-2 text-sm font-mono transition-colors ${
                            index === autocompleteIndex
                              ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                              : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                          }`}
                        >
                          {field}
                        </button>
                      ))}
                    </div>
                  )}
                  
                  {/* Field Suggestions (Browse All) */}
                  {showFieldSuggestions && commonFields.length > 0 && (
                    <div className="mt-2 p-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg max-h-32 overflow-y-auto">
                      <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">All available fields ({commonFields.length}):</p>
                      <div className="flex flex-wrap gap-1">
                        {commonFields.map(field => (
                          <button
                            key={field}
                            onClick={() => {
                              setJsonbPath(field);
                              setShowFieldSuggestions(false);
                            }}
                            className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 hover:bg-blue-100 dark:hover:bg-blue-900/30 text-gray-700 dark:text-gray-300 hover:text-blue-700 dark:hover:text-blue-300 rounded border border-gray-200 dark:border-gray-700 transition-colors font-mono"
                          >
                            {field}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                
                <div className="grid grid-cols-3 gap-2">
                  {/* JSONB Operator */}
                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Operator
                    </label>
                    <select
                      value={jsonbOperator}
                      onChange={(e) => setJsonbOperator(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                    >
                      <option value="=">=</option>
                      <option value="!=">!=</option>
                      <option value=">">&gt;</option>
                      <option value="<">&lt;</option>
                      <option value=">=">&gt;=</option>
                      <option value="<=">&lt;=</option>
                      <option value="CONTAINS">Contains</option>
                      <option value="STARTS_WITH">Starts with</option>
                      <option value="ENDS_WITH">Ends with</option>
                      <option value="LIKE">LIKE (wildcards)</option>
                      <option value="ILIKE">ILIKE (case-insensitive)</option>
                    </select>
                  </div>
                  
                  {/* JSONB Value */}
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Value {jsonbOperator.includes('LIKE') && '(use * for wildcards)'}
                    </label>
                    <input
                      type="text"
                      value={jsonbValue}
                      onChange={(e) => setJsonbValue(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addJsonbQuery()}
                      placeholder={
                        jsonbOperator.includes('LIKE') ? 'e.g., admin*, *temp*' :
                        jsonbOperator === 'CONTAINS' ? 'e.g., temp' :
                        jsonbOperator === 'STARTS_WITH' ? 'e.g., admin' :
                        jsonbOperator === 'ENDS_WITH' ? 'e.g., .exe' :
                        'e.g., value'
                      }
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm font-mono"
                    />
                  </div>
                </div>
                
                {/* Add Query Button */}
                <button
                  onClick={addJsonbQuery}
                  disabled={!jsonbPath.trim()}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <PlusIcon className="w-4 h-4" />
                  Add Filter to Query
                </button>
              </div>
            </div>
          </div>

          {/* Date Range Filters */}
          <div>
            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Date Range
            </h4>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Start Date
                </label>
                <div className="relative">
                  <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                  <input
                    type="datetime-local"
                    value={startDate}
                    onChange={(e) => { setStartDate(e.target.value); setPage(0); }}
                    className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  End Date
                </label>
                <div className="relative">
                  <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                  <input
                    type="datetime-local"
                    value={endDate}
                    onChange={(e) => { setEndDate(e.target.value); setPage(0); }}
                    className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Filter Actions */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="w-full px-4 py-2 bg-red-100 hover:bg-red-200 dark:bg-red-900/30 dark:hover:bg-red-900/50 text-red-700 dark:text-red-300 rounded-lg text-sm font-medium transition-colors"
            >
              Clear All Filters
            </button>
          )}
        </div>
      </div>
    </div>
    </>
  );
};

export default TimelineViewer;
