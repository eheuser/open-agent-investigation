/**
 * Tool execution card component.
 * Displays tool calls as expandable cards.
 */
import React, { useState } from 'react';
import { ChatMessage, ToolExecution } from '../../hooks/useInvestigationChat';
import { ChevronDownIcon, ChevronRightIcon, MagnifyingGlassIcon, ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline';
import EventCard from './EventCard';

interface ToolExecutionCardProps {
  message?: ChatMessage;
  // Allow passing a single tool execution directly
  toolExecution?: ToolExecution;
  // Callback to replicate query in Events tab
  onReplicateQuery?: (queryParams: any) => void;
  searchQuery?: string;
}

const ToolExecutionCard: React.FC<ToolExecutionCardProps> = ({ message, toolExecution, onReplicateQuery }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copiedArgs, setCopiedArgs] = useState(false);
  const [copiedResult, setCopiedResult] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());

  // Support both message-based and direct tool execution props
  const te = toolExecution;
  const toolName = te?.tool_name || message?.metadata?.tool_name || 'Unknown Tool';
  const displayName = te?.display_name || message?.metadata?.tool_display_name || toolName;
  const args = te?.arguments || message?.metadata?.tool_arguments || {};
  const result = te?.result || message?.metadata?.tool_result;
  const resultSummary = te?.result_summary || message?.metadata?.tool_result_summary;
  const status = te?.status || message?.metadata?.tool_status || 'executing';
  const executionNumber = te?.execution_number || message?.metadata?.execution_number;
  const maxTools = te?.max_tools || message?.metadata?.max_tools;

  // Check if this is a timeline registration tool
  const isTimelineTool = toolName === 'register_timeline_entry' || toolName === 'register_finding';

  // Check if this is a RAG tool (query expansion or source retrieval)
  const isRagTool = toolName === 'expand_query' || toolName === 'retrieve_sources';

  // Check if this is a JSONB query tool that can be replicated
  const isJsonbQueryTool = toolName === 'query_jsonb_field' || toolName === 'query_jsonb_multiple';

  // Check if this is an event search tool that can be replicated
  const isEventSearchTool = toolName === 'search_events_by_type' ||
    toolName === 'search_events_by_timerange' ||
    toolName === 'search_events_by_content';

  // Extract query parameters for replication
  const canReplicate = (isJsonbQueryTool || isEventSearchTool) && args && onReplicateQuery;

  const handleReplicateQuery = () => {
    if (!canReplicate) return;

    // Extract query parameters based on tool type
    let queryParams: any = {};

    if (toolName === 'query_jsonb_field') {
      // Single field query
      // Note: The tool uses 'jsonb_path' but the UI uses 'field_path' in some contexts
      const fieldPath = args.jsonb_path || args.field_path || '';
      const operator = args.operator || '=';
      const value = args.value || '';
      const eventType = args.event_type || null;

      queryParams = {
        jsonbQueries: [{
          id: `${Date.now()}-replicated`,
          path: fieldPath,
          operator: operator,
          value: value
        }],
        // Include event_type filter if present
        eventType: eventType
      };
    } else if (toolName === 'query_jsonb_multiple') {
      // Multiple field queries
      const conditions = args.conditions || [];
      const eventType = args.event_type || null;

      queryParams = {
        jsonbQueries: conditions.map((cond: any, idx: number) => ({
          id: `${Date.now()}-${idx}`,
          path: cond.jsonb_path || cond.field_path || '',
          operator: cond.operator || '=',
          value: cond.value || ''
        })),
        // Include event_type filter if present
        eventType: eventType
      };
    } else if (toolName === 'search_events_by_type') {
      // Event type search
      queryParams = {
        eventType: args.event_type || ''
      };
    } else if (toolName === 'search_events_by_timerange') {
      // Time range search
      queryParams = {
        startDate: args.start_time || '',
        endDate: args.end_time || '',
        eventType: args.event_type || null
      };
    } else if (toolName === 'search_events_by_content') {
      // Content search
      queryParams = {
        searchText: args.search_text || args.search_term || '',
        eventType: args.event_type || null
      };
    }

    onReplicateQuery(queryParams);
  };

  // Check if the result indicates a duplicate or new entry
  let isDuplicate = false;
  let isNewEntry = false;
  let timelineMessage = '';

  if (isTimelineTool && result && typeof result === 'object') {
    isDuplicate = result.is_duplicate === true;
    isNewEntry = result.entry_id && !isDuplicate;

    if (isDuplicate) {
      timelineMessage = result.message || `Event ${result.event_id} is already on the timeline`;
    } else if (isNewEntry) {
      timelineMessage = `Added to timeline: ${result.title || 'New entry'}`;
    }
  }

  return (
    <div className="flex justify-start w-full">
      <div className="w-full max-w-4xl bg-indigo-50 dark:bg-indigo-900/20 rounded-lg border border-indigo-200 dark:border-indigo-800 shadow-sm">
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-indigo-100 dark:hover:bg-indigo-900/30 rounded-t-lg"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDownIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
              ) : (
                <ChevronRightIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-900 dark:text-gray-100 text-sm truncate">
                  {displayName}
                </span>
                {executionNumber && maxTools && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                    ({executionNumber}/{maxTools})
                  </span>
                )}
              </div>
              {/* Show timeline-specific message or result summary */}
              {isTimelineTool && timelineMessage ? (
                <div className={`text-xs mt-0.5 font-medium truncate ${isDuplicate
                  ? 'text-amber-700 dark:text-amber-300'
                  : 'text-green-700 dark:text-green-300'
                  }`}>
                  {timelineMessage}
                </div>
              ) : resultSummary ? (
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 truncate">
                  {resultSummary}
                </div>
              ) : null}
            </div>
          </div>

          {/* Replicate Query Button - Only show for JSONB query tools when expanded */}
          {isExpanded && canReplicate && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleReplicateQuery();
              }}
              className="flex items-center gap-1 px-2 py-1 text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded text-xs transition-colors mr-2"
              title="Query in Events tab"
            >
              <MagnifyingGlassIcon className="w-3.5 h-3.5" />
              <span className="text-xs">Query</span>
            </button>
          )}

          {/* Status indicator */}
          <div className="flex-shrink-0">
            {status === 'executing' && (
              <span className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                <span className="animate-pulse">●</span>
                Executing
              </span>
            )}
            {status === 'completed' && (
              <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <span>✓</span>
                Complete
              </span>
            )}
            {status === 'failed' && (
              <span className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                <span>✗</span>
                Failed
              </span>
            )}
          </div>
        </div>

        {/* Expanded details */}
        {isExpanded && (
          <div className="px-4 py-3 border-t border-indigo-200 dark:border-indigo-800">
            {/* Arguments */}
            {Object.keys(args).length > 0 && (
              <div className="mb-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs font-medium text-gray-600 dark:text-gray-400">
                    Arguments:
                  </div>
                  <button
                    onClick={async () => {
                      await navigator.clipboard.writeText(JSON.stringify(args, null, 2));
                      setCopiedArgs(true);
                      setTimeout(() => setCopiedArgs(false), 2000);
                    }}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-opacity"
                    title="Copy arguments"
                  >
                    {copiedArgs ? (
                      <CheckIcon className="w-3 h-3 text-green-600" />
                    ) : (
                      <ClipboardDocumentIcon className="w-3 h-3 text-gray-500" />
                    )}
                  </button>
                </div>
                {/* Use key-value display for better readability */}
                <div className="bg-white dark:bg-gray-900 rounded p-3 space-y-1.5">
                  {Object.entries(args).map(([key, value]) => (
                    <div key={key} className="flex items-start gap-2 text-xs">
                      <span className="font-medium text-blue-600 dark:text-blue-400 min-w-[120px] flex-shrink-0">
                        {key}:
                      </span>
                      <span className="text-gray-800 dark:text-gray-200 font-mono break-all">
                        {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Result */}
            {result && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs font-medium text-gray-600 dark:text-gray-400">
                    Result:
                  </div>
                  <button
                    onClick={async () => {
                      const resultText = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
                      await navigator.clipboard.writeText(resultText);
                      setCopiedResult(true);
                      setTimeout(() => setCopiedResult(false), 2000);
                    }}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-opacity"
                    title="Copy result"
                  >
                    {copiedResult ? (
                      <CheckIcon className="w-3 h-3 text-green-600" />
                    ) : (
                      <ClipboardDocumentIcon className="w-3 h-3 text-gray-500" />
                    )}
                  </button>
                </div>

                {/* Check if this is query expansion result */}
                {typeof result === 'object' && (result.formatted_queries || result.expanded_terms) ? (
                  <div className="space-y-2">
                    {result.formatted_queries && Array.isArray(result.formatted_queries) ? (
                      /* New formatted display */
                      <div className="space-y-2">
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                          Generated {result.total_queries || result.formatted_queries.length} search queries
                        </div>
                        {result.formatted_queries.map((item: any, idx: number) => {
                          const typeColors: Record<string, string> = {
                            'question': 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
                            'keyword_phrase': 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
                            'artifact_specific': 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
                            'technique': 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
                          };
                          const typeLabels: Record<string, string> = {
                            'question': 'Question',
                            'keyword_phrase': 'Keywords',
                            'artifact_specific': 'Artifact',
                            'technique': 'Technique',
                          };
                          const colorClass = typeColors[item.type] || 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300';
                          const typeLabel = typeLabels[item.type] || 'Query';

                          return (
                            <div key={idx} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                              <div className="flex items-start gap-3">
                                <span className="text-xs font-bold text-gray-400 dark:text-gray-500 flex-shrink-0 w-6">
                                  {item.number}.
                                </span>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${colorClass}`}>
                                      {typeLabel}
                                    </span>
                                  </div>
                                  <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                                    {item.query}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      /* Fallback for old format (just expanded_terms array) */
                      <div className="space-y-2">
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                          Generated {result.expanded_terms.length} search queries
                        </div>
                        {result.expanded_terms.map((term: string, idx: number) => (
                          <div key={idx} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                            <div className="flex items-start gap-3">
                              <span className="text-xs font-bold text-gray-400 dark:text-gray-500 flex-shrink-0 w-6">
                                {idx + 1}.
                              </span>
                              <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                                {term}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : /* Check if result contains events array (agent tools) */
                  /* Handle both direct result.events and nested result.result.events */
                  typeof result === 'object' && (
                    (result.events && Array.isArray(result.events)) ||
                    (result.result?.events && Array.isArray(result.result.events))
                  ) ? (
                    (() => {
                      // Handle both direct and nested result structures
                      const events = result.events || result.result?.events || [];
                      const count = result.count || result.result?.count || events.length;

                      return (
                        <div className="space-y-2">
                          <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                            {count} event{count !== 1 ? 's' : ''} found
                          </div>
                          {events.map((event: any, idx: number) => (
                            <EventCard key={`event-${idx}`} event={event} isQueryResult={true} />
                          ))}
                        </div>
                      );
                    })()
                  ) : /* Check if result contains entries array (analysis module results) */
                    typeof result === 'object' && result.entries && Array.isArray(result.entries) ? (
                      (() => {
                        const entries = result.entries;
                        const total = result.total || entries.length;
                        const page = result.page || 1;
                        const totalPages = result.total_pages || 1;

                        return (
                          <div className="space-y-2">
                            <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                              {total} entr{total !== 1 ? 'ies' : 'y'} found (page {page}/{totalPages})
                            </div>
                            {entries.map((entry: any, idx: number) => {
                              // Analysis module entries have an event_id field that links to the full event
                              // We need to convert them to event format for EventCard
                              if (entry.event_id) {
                                // Create a pseudo-event from the entry
                                const pseudoEvent = {
                                  event_id: entry.event_id,
                                  event_type: entry.event_type || 'analysis_entry',
                                  timestamp: entry.timestamp || entry.last_modified || entry.last_visit_time || entry.created,
                                  artifact_id: entry.artifact_id,
                                  payload: entry,
                                };
                                return <EventCard key={`entry-${idx}`} event={pseudoEvent} isQueryResult={true} />;
                              }

                              // Fallback: render as simple card
                              return (
                                <div key={`entry-${idx}`} className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-800 p-3">
                                  <div className="text-sm text-gray-700 dark:text-gray-300">
                                    {JSON.stringify(entry, null, 2)}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })()
                    ) : /* Check if result contains RAG sources */
                      typeof result === 'object' && result.sources && Array.isArray(result.sources) ? (
                        <div className="space-y-2">
                          <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                            {result.sources.length} source{result.sources.length !== 1 ? 's' : ''} retrieved
                          </div>
                          {result.sources.map((source: any, idx: number) => {
                            // RAG sources contain:
                            // - owner_type: 'tool' (for events), 'timeline', 'chat', etc.
                            // - owner_id: event_id for tool-type sources
                            // - text_preview: Short preview text
                            // - text_full: Full formatted text
                            // - event: Full event object (for tool-type sources)
                            // - score: Similarity score

                            const isEventSource = source.owner_type === 'tool';
                            const eventId = isEventSource ? source.owner_id : null;

                            // Check if we have full event data
                            const hasEventData = source.event &&
                              typeof source.event === 'object' &&
                              source.event !== null &&
                              (source.event.event_id || source.event.event_type);

                            // If we have full event data, use EventCard
                            if (hasEventData) {
                              return (
                                <div key={`source-${idx}`} className="space-y-1">
                                  {/* Score header */}
                                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 px-1">
                                    <span className="font-medium">#{source.index || idx + 1}</span>
                                    {source.score !== undefined && (
                                      <span className="px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 font-medium">
                                        Score: {source.score.toFixed(3)}
                                      </span>
                                    )}
                                  </div>
                                  {/* Event card */}
                                  <EventCard event={source.event} isQueryResult={true} />
                                </div>
                              );
                            }

                            // Fallback: Render as a simple source card
                            return (
                              <div key={`source-${idx}`} className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-800 p-3">
                                {/* Header with badges */}
                                <div className="flex items-center justify-between mb-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                                      #{source.index || idx + 1}
                                    </span>
                                    <span className="text-xs px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                                      {source.owner_type}
                                    </span>
                                    {isEventSource && eventId && (
                                      <span className="text-xs text-gray-500 dark:text-gray-400">
                                        Event #{eventId}
                                      </span>
                                    )}
                                  </div>
                                  {source.score !== undefined && (
                                    <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 font-medium">
                                      Score: {source.score.toFixed(3)}
                                    </span>
                                  )}
                                </div>

                                {/* Preview text */}
                                <div className="text-sm text-gray-700 dark:text-gray-300">
                                  {source.text_preview || source.text_full?.substring(0, 200) || 'No preview available'}
                                </div>

                                {/* Show full details - either event data or raw text */}
                                {source.text_full && source.text_full.length > (source.text_preview?.length || 0) && (
                                  <details className="mt-2">
                                    <summary className="text-xs text-blue-600 dark:text-blue-400 cursor-pointer hover:underline">
                                      ▶ Show full details
                                    </summary>
                                    <div className="mt-2 text-xs bg-gray-50 dark:bg-gray-900 p-3 rounded max-h-96 overflow-y-auto">
                                      <pre className="font-mono whitespace-pre-wrap break-all text-gray-600 dark:text-gray-400 text-xs leading-relaxed">
                                        {source.text_full}
                                      </pre>
                                    </div>
                                  </details>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : typeof result === 'object' && !Array.isArray(result) && Object.keys(result).length <= 10 ? (
                        /* Simple object result - use key-value display */
                        <div className="bg-white dark:bg-gray-900 rounded p-3 space-y-1.5">
                          {Object.entries(result).map(([key, value]) => (
                            <div key={key} className="flex items-start gap-2 text-xs">
                              <span className="font-medium text-green-600 dark:text-green-400 min-w-[120px] flex-shrink-0">
                                {key}:
                              </span>
                              <span className="text-gray-800 dark:text-gray-200 font-mono break-all">
                                {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        /* Fallback to JSON display for complex results */
                        <div className="bg-white dark:bg-gray-900 rounded p-2 text-xs font-mono overflow-x-auto max-h-96">
                          <pre className="text-gray-800 dark:text-gray-200">
                            {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
                          </pre>
                        </div>
                      )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ToolExecutionCard;
