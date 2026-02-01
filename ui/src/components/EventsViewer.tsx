import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import TypedDictionaryViewer from './TypedDictionaryViewer';
import { 
  MagnifyingGlassIcon, 
  FunnelIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CalendarIcon,
  XMarkIcon,
  DocumentTextIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  LightBulbIcon,
  PlusIcon
} from '@heroicons/react/24/outline';

interface Props {
  investigationId: string;
  onClose?: () => void;
  replicatedQuery?: any;
  onQueryApplied?: () => void;
}

interface Event {
  event_id: number;
  event_ts: string;
  artifact_id: number | null;
  event_type: string;
  payload: any;
}

interface EventsResponse {
  events: Event[];
  count: number;
  total: number;
  limit: number;
  offset: number;
}

interface JsonbQuery {
  id: string;
  path: string;
  operator: string;
  value: string;
}

const EventsViewer: React.FC<Props> = ({ investigationId, onClose, replicatedQuery, onQueryApplied }) => {
  const { subscribe } = useWebSocketContext();
  const [events, setEvents] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [limit] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Error modal state
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>('');
  
  // Filters
  const [searchText, setSearchText] = useState('');
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  
  // JSONB Query Filters
  const [jsonbPath, setJsonbPath] = useState('');
  const [jsonbOperator, setJsonbOperator] = useState('=');
  const [jsonbValue, setJsonbValue] = useState('');
  const [showFieldSuggestions, setShowFieldSuggestions] = useState(false);
  const [commonFields, setCommonFields] = useState<string[]>([]);
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [autocompleteIndex, setAutocompleteIndex] = useState(0);
  
  // Event type filtering
  const [availableEventTypes, setAvailableEventTypes] = useState<Array<{event_type: string, count: number}>>([]);
  const [showEventTypeDropdown, setShowEventTypeDropdown] = useState(false);
  
  // JSONB Query Breadcrumbs
  const [jsonbQueries, setJsonbQueries] = useState<JsonbQuery[]>([]);
  
  // Apply replicated query from chat
  useEffect(() => {
    if (replicatedQuery) {
      // Apply JSONB queries if present
      if (replicatedQuery.jsonbQueries) {
        setJsonbQueries(replicatedQuery.jsonbQueries);
      }
      
      // Apply event_type filter if present
      if (replicatedQuery.eventType) {
        setEventTypeFilter(replicatedQuery.eventType);
      }
      
      // Apply search text if present
      if (replicatedQuery.searchText) {
        setSearchText(replicatedQuery.searchText);
      }
      
      // Apply date range if present
      if (replicatedQuery.startDate) {
        try {
          // Convert ISO timestamp to datetime-local format (YYYY-MM-DDTHH:mm)
          const date = new Date(replicatedQuery.startDate);
          if (!isNaN(date.getTime())) {
            const formattedDate = date.toISOString().slice(0, 16);
            setStartDate(formattedDate);
          }
        } catch (e) {
          console.error('Failed to parse start date:', e);
        }
      }
      if (replicatedQuery.endDate) {
        try {
          // Convert ISO timestamp to datetime-local format (YYYY-MM-DDTHH:mm)
          const date = new Date(replicatedQuery.endDate);
          if (!isNaN(date.getTime())) {
            const formattedDate = date.toISOString().slice(0, 16);
            setEndDate(formattedDate);
          }
        } catch (e) {
          console.error('Failed to parse end date:', e);
        }
      }
      
      setPage(0);
      
      // Clear the replicated query to prevent re-application
      if (onQueryApplied) {
        onQueryApplied();
      }
    }
  }, [replicatedQuery, onQueryApplied]);
  
  // Expanded event details
  const [expandedEventIds, setExpandedEventIds] = useState<Set<number>>(new Set());
  
  // Adding to timeline
  const [addingToTimeline, setAddingToTimeline] = useState<number | null>(null);
  



  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: (page * limit).toString(),
      });
      
      if (startDate) {
        params.append('start_date', startDate);
      }
      
      if (endDate) {
        params.append('end_date', endDate);
      }
      
      if (searchText) {
        params.append('search', searchText);
      }
      
      if (eventTypeFilter) {
        params.append('event_type', eventTypeFilter);
      }
      
      // Add JSONB query parameters from breadcrumbs
      jsonbQueries.forEach((query, index) => {
        params.append(`jsonb_path_${index}`, query.path);
        params.append(`jsonb_operator_${index}`, query.operator);
        if (query.value) {
          params.append(`jsonb_value_${index}`, query.value);
        }
      });
      
      params.append('order', sortOrder);
      
      const response = await api.get<EventsResponse>(
        `/api/v1/events/${investigationId}?${params.toString()}`
      );
      
      setEvents(response.data.events || []);
      const newTotal = response.data.total || 0;
      setTotal(newTotal);
      
      // Note: commonFields are now fetched via the dedicated /fields endpoint
      // This ensures we get all available fields, not just from the current page
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load events');
      console.error('Failed to fetch events:', err);
    } finally {
      setLoading(false);
    }
  }, [investigationId, page, limit, startDate, endDate, searchText, eventTypeFilter, sortOrder, jsonbQueries]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);
  
  // Fetch available JSONB fields (updates when event type filter changes)
  useEffect(() => {
    const fetchAvailableFields = async () => {
      try {
        // Build URL with optional event_type parameter
        let url = `/api/v1/events/${investigationId}/fields`;
        if (eventTypeFilter) {
          url += `?event_type=${encodeURIComponent(eventTypeFilter)}`;
        }
        
        const response = await api.get<{ fields: string[]; count: number; event_types_sampled: number }>(
          url
        );
        
        if (response.data && response.data.fields) {
          setCommonFields(response.data.fields);
        } else {
          console.warn('No fields returned from API');
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
  
  // Fetch available event types on mount
  useEffect(() => {
    const fetchEventTypes = async () => {
      try {
        const response = await api.get<{ event_types: Array<{event_type: string, count: number}>; total_types: number }>(
          `/api/v1/events/${investigationId}/event-types`
        );
        
        if (response.data.event_types.length > 0) {
          setAvailableEventTypes(response.data.event_types);
          //console.log(`Loaded ${response.data.total_types} event types`);
        }
      } catch (err) {
        console.error('Failed to fetch event types:', err);
      }
    };
    
    fetchEventTypes();
  }, [investigationId]); // Only run on mount or when investigationId changes

  // Subscribe to WebSocket messages for real-time updates
  useEffect(() => {
    const handleEventsMessage = (message: any) => {
      // Listen for events_inserted messages
      if (message.type === 'events_inserted') {
        //console.log(`New events inserted: ${message.count}`);
        // Refresh events list
        fetchEvents();
      }
      
      // Also listen for graph_mutated which might add events
      if (message.type === 'graph_mutated') {
        // Refresh in case events were added
        fetchEvents();
      }
    };

    const unsubscribe = subscribe(handleEventsMessage);
    return unsubscribe;
  }, [subscribe, fetchEvents]);

  const handleSearch = () => {
    setPage(0); // Reset to first page
    fetchEvents();
  };

  const clearFilters = () => {
    setSearchText('');
    setEventTypeFilter('');
    setStartDate('');
    setEndDate('');
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
    setPage(0); // Reset to first page when changing sort
  };

  // Helper function to highlight matching text
  const highlightText = (text: string, searchTerms: string[]) => {
    if (!searchTerms.length || !text) return text;
    
    let highlightedText = String(text);
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
    if (searchText) terms.push(searchText);
    return terms;
  };
  
  const searchTerms = getSearchTerms();
  const totalPages = Math.ceil(total / limit);
  const hasActiveFilters = searchText || eventTypeFilter || startDate || endDate || jsonbQueries.length > 0;
  
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

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  const formatPayload = (payload: any) => {
    if (typeof payload === 'string') {
      try {
        return JSON.parse(payload);
      } catch {
        return payload;
      }
    }
    return payload;
  };
  
  // Filter fields based on current input
  const getFilteredFields = () => {
    if (!jsonbPath) return commonFields;
    const searchTerm = jsonbPath.toLowerCase();
    return commonFields.filter(field => 
      field.toLowerCase().includes(searchTerm)
    );
  };
  
  const filteredFields = getFilteredFields();
  
  // Handle field path input changes
  const handleJsonbPathChange = (value: string) => {
    setJsonbPath(value);
    setShowAutocomplete(value.length > 0 && commonFields.length > 0);
    setAutocompleteIndex(0);
  };
  
  // Handle keyboard navigation in autocomplete
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
  
  // Select field from autocomplete
  const selectField = (field: string) => {
    setJsonbPath(field);
    setShowAutocomplete(false);
  };
  
  const addEventToTimeline = async (event: Event) => {
    setAddingToTimeline(event.event_id);
    try {
      // Create timeline entry from event
      await api.post(`/api/v1/timeline/${investigationId}/entries`, {
        event_id: event.event_id,
        timestamp: event.event_ts,
        entry_type: 'event',
        title: `Event: ${event.event_type}`,
        description: `Added from events viewer`,
        tags: [],
        is_visible: true
      });
      
      // Event added successfully
      
      // Show a temporary success indicator
      setTimeout(() => {
        setAddingToTimeline(null);
      }, 1000);
    } catch (err: any) {
      console.error('Failed to add event to timeline:', err);
      
      // Check if event is already on timeline
      if (err.response?.status === 409) {
        setErrorMessage('This event is already on the timeline');
      } else {
        setErrorMessage(err.response?.data?.detail || err.message || 'Failed to add event to timeline');
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
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 rounded-lg transition-colors"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}
      
    <div className="flex h-full bg-white dark:bg-gray-900">
      {/* Left Column - Events List */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {hasActiveFilters ? (
                  <>
                    {total.toLocaleString()} filtered
                    <span className="text-xs ml-1">(of all events)</span>
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

          {/* Event Type Filter Badge */}
          {eventTypeFilter && (
            <div className="mb-2">
              <div className="inline-flex items-center gap-1.5 px-2 py-1 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded-md text-xs">
                <span className="text-purple-700 dark:text-purple-300 font-medium">Event Type:</span>
                <span className="text-purple-900 dark:text-purple-200 font-mono">{eventTypeFilter}</span>
                <button
                  onClick={() => {
                    setEventTypeFilter('');
                    setPage(0);
                  }}
                  className="ml-1 p-0.5 hover:bg-purple-100 dark:hover:bg-purple-900/30 rounded transition-colors"
                  title="Remove event type filter"
                >
                  <XMarkIcon className="w-3 h-3 text-purple-600 dark:text-purple-400" />
                </button>
              </div>
            </div>
          )}

          {/* JSONB Query Breadcrumbs - Always Visible */}
          {jsonbQueries.length > 0 && (
          <div className="mb-3 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
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

          {/* Search Bar */}
          <div className="flex gap-2">
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search events..."
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

        {/* Events List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Loading events...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <p className="text-red-600 dark:text-red-400 mb-2">Error loading events</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
                <button
                  onClick={fetchEvents}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
                >
                  Retry
                </button>
              </div>
            </div>
          ) : events.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md px-4">
                <DocumentTextIcon className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No Events Found
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {hasActiveFilters
                    ? 'Try adjusting your filters or search criteria.'
                    : 'Upload artifacts or paste event data to get started.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {events.map((event) => (
                <div
                  key={event.event_id}
                  className="p-3"
                >
                  {/* Event Header - Clickable */}
                  <div 
                    className="flex items-start justify-between gap-3 mb-1 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 -mx-3 -mt-3 px-3 pt-3 pb-1 rounded-t transition-colors"
                    onClick={() => {
                      const newExpanded = new Set(expandedEventIds);
                      if (newExpanded.has(event.event_id)) {
                        newExpanded.delete(event.event_id);
                      } else {
                        newExpanded.add(event.event_id);
                      }
                      setExpandedEventIds(newExpanded);
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span 
                          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300"
                          dangerouslySetInnerHTML={{ __html: highlightText(event.event_type, searchTerms) }}
                        />
                        {event.artifact_id && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            Artifact #{event.artifact_id}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {formatTimestamp(event.event_ts)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Add to Timeline Button - Only show when event is expanded */}
                      {expandedEventIds.has(event.event_id) && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            addEventToTimeline(event);
                          }}
                          disabled={addingToTimeline === event.event_id}
                          className="flex items-center gap-1 px-2 py-1 bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 text-white rounded text-xs font-medium transition-colors"
                          title="Add to timeline"
                        >
                          {addingToTimeline === event.event_id ? (
                            <>
                              <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                              Adding...
                            </>
                          ) : (
                            <>
                              <PlusIcon className="w-3 h-3" />
                              Add to Timeline
                            </>
                          )}
                        </button>
                      )}
                      <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                        #{event.event_id}
                      </span>
                    </div>
                  </div>

                  {/* Event Payload Preview */}
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    {expandedEventIds.has(event.event_id) ? (
                      <div className="mt-2">
                        <TypedDictionaryViewer
                          data={formatPayload(event.payload)}
                          title=""
                          onAddToTimeline={(key, value) => {
                            // Could implement adding specific fields to timeline
                            //console.log('Add to timeline:', key, value);
                          }}
                        />
                      </div>
                    ) : (
                      searchTerms.length > 0 ? (
                        <p 
                          className="truncate text-xs text-gray-500 dark:text-gray-400"
                          dangerouslySetInnerHTML={{
                            __html: highlightText(
                              typeof event.payload === 'string'
                                ? event.payload.substring(0, 100)
                                : JSON.stringify(event.payload).substring(0, 100),
                              searchTerms
                            ) + ((typeof event.payload === 'string' ? event.payload.length : JSON.stringify(event.payload).length) > 100 ? '...' : '')
                          }}
                        />
                      ) : (
                        <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                          {typeof event.payload === 'string'
                            ? event.payload.substring(0, 100)
                            : JSON.stringify(event.payload).substring(0, 100)}
                          {(typeof event.payload === 'string' ? event.payload.length : JSON.stringify(event.payload).length) > 100 && '...'}
                        </p>
                      )
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {!loading && events.length > 0 && (
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
          {/* Event Type Filter Section */}
          <div>
            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Event Type Filter
            </h4>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Filter events by type (e.g., "evtx_security_4624", "mft_entry")
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
                JSONB Field Query
              </h4>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                Query specific fields within event payloads (e.g., "SubjectUserName", "TargetUserName", "ProcessName")
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
                        'e.g., administrator'
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
                
                {/* Example queries */}
                <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                  <p className="text-xs font-medium text-blue-900 dark:text-blue-300 mb-1">Examples:</p>
                  <ul className="text-xs text-blue-800 dark:text-blue-400 space-y-0.5 ml-3">
                    <li>• Field: <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">SubjectUserName</code> = <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">admin</code></li>
                    <li>• Field: <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">ProcessName</code> ILIKE <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">*powershell*</code></li>
                    <li>• Field: <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">EventID</code> = <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">4624</code></li>
                  </ul>
                </div>
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
                    onChange={(e) => setStartDate(e.target.value)}
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
                    onChange={(e) => setEndDate(e.target.value)}
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

export default EventsViewer;
