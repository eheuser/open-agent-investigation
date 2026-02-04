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
                <div className={`text-xs mt-0.5 font-medium truncate ${
                  isDuplicate 
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
                <div className="bg-white dark:bg-gray-900 rounded p-2 text-xs font-mono overflow-x-auto">
                  <pre className="text-gray-800 dark:text-gray-200">
                    {JSON.stringify(args, null, 2)}
                  </pre>
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
                
                {/* Check if result contains events array */}
                {typeof result === 'object' && result.events && Array.isArray(result.events) ? (
                  <div className="space-y-2">
                    <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                      {result.count || result.events.length} event{(result.count || result.events.length) !== 1 ? 's' : ''} found
                    </div>
                    {result.events.slice(0, 5).map((event: any, idx: number) => (
                      <EventCard key={`event-${idx}`} event={event} isQueryResult={true} />
                    ))}
                    {result.events.length > 5 && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-2">
                        ... and {result.events.length - 5} more events
                      </div>
                    )}
                  </div>
                ) : (
                  /* Fallback to JSON display */
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
