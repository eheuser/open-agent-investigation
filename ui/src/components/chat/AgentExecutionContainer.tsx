/**
 * Collapsible agent execution container.
 * Displays agent investigation progress with expandable tool execution cards.
 * Matches the style of the event parsing banner.
 */
import React, { useState } from 'react';
import { ChevronDownIcon, ChevronRightIcon, CpuChipIcon } from '@heroicons/react/24/outline';
import { ToolExecution } from '../../hooks/useInvestigationChat';
import ToolExecutionCard from './ToolExecutionCard';

interface AgentExecutionContainerProps {
  toolExecutions: ToolExecution[];
  isStreaming?: boolean;
  onReplicateQuery?: (queryParams: any) => void;
  // Investigation stats
  stats?: {
    events_analyzed?: number;
    timeline_entries_created?: number;
    turns_executed?: number;
  };
}

const AgentExecutionContainer: React.FC<AgentExecutionContainerProps> = ({
  toolExecutions,
  isStreaming,
  onReplicateQuery,
  stats,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Calculate current turn number from tool executions
  const currentTurn = toolExecutions.length > 0
    ? Math.max(...toolExecutions.map(t => t.execution_number || 0))
    : 0;

  // Get max turns from latest tool execution
  const maxTurns = toolExecutions.length > 0
    ? toolExecutions[toolExecutions.length - 1]?.max_tools || 0
    : 0;

  // Count completed tools
  const completedTools = toolExecutions.filter(t => t.status === 'completed').length;
  const totalTools = toolExecutions.length;

  // Count timeline entries added
  // Prefer stats.timeline_entries_created (from backend) over tool execution counting
  const timelineEntriesFromTools = toolExecutions.filter(
    t => {
      if (t.status !== 'completed' || !t.result || typeof t.result !== 'object') {
        return false;
      }
      
      // register_timeline_entry: check for entry_id AND is_duplicate === false
      if (t.tool_name === 'register_timeline_entry') {
        return t.result.entry_id && t.result.is_duplicate === false;
      }
      
      // register_finding: always counts if it has entry_id (no is_duplicate field)
      if (t.tool_name === 'register_finding') {
        return !!t.result.entry_id;
      }
      
      return false;
    }
  ).length;

  // Use stats.timeline_entries_created if available, otherwise use tool count
  const timelineEntriesAdded = stats?.timeline_entries_created ?? timelineEntriesFromTools;

  // Calculate events seen from tool executions in real-time
  // Include both completed AND executing tools (for live updates)
  const eventsSeen = toolExecutions.reduce((total, t) => {
    if (t.result && typeof t.result === 'object') {
      // Check for count field (from search tools)
      if ('count' in t.result && typeof t.result.count === 'number') {
        return total + t.result.count;
      }
      // Check for events array (from query tools)
      if ('events' in t.result && Array.isArray(t.result.events)) {
        return total + t.result.events.length;
      }
    }
    
    // Fallback: Parse result_summary for "Found X events" pattern
    if (t.result_summary && typeof t.result_summary === 'string') {
      const match = t.result_summary.match(/Found (\d+) events?/i);
      if (match) {
        return total + parseInt(match[1], 10);
      }
    }
    
    return total;
  }, 0);

  // Use stats.events_analyzed if available (when complete), otherwise show live count from tools
  const eventsAnalyzed = stats?.events_analyzed || eventsSeen;

  // Format numbers with commas for readability
  const formatNumber = (num: number): string => {
    return num.toLocaleString();
  };

  return (
    <div className="my-4">
      {/* Collapsible header - matches event parsing banner style */}
      <div
        className={`border rounded-lg transition-all ${
          isStreaming
            ? 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20'
            : 'border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800'
        }`}
      >
        <div
          className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition-colors"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {/* Expand/collapse icon */}
            <div className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDownIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              ) : (
                <ChevronRightIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              )}
            </div>

            {/* Agent icon */}
            <div className="flex-shrink-0">
              <div className={`p-2 rounded-full ${
                isStreaming
                  ? 'bg-blue-100 dark:bg-blue-800'
                  : 'bg-gray-200 dark:bg-gray-700'
              }`}>
                <CpuChipIcon className={`w-5 h-5 ${
                  isStreaming
                    ? 'text-blue-600 dark:text-blue-400'
                    : 'text-gray-600 dark:text-gray-400'
                }`} />
              </div>
            </div>

            {/* Status text */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-900 dark:text-white text-sm">
                  Agent Investigation
                </span>
                {isStreaming && (
                  <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                    Running...
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                {isStreaming ? (
                  <span>Executing turn {currentTurn} of {maxTurns}</span>
                ) : (
                  <span>Completed {completedTools} tool executions</span>
                )}
              </div>
            </div>

            {/* Stats badges */}
            <div className="flex items-center gap-3 flex-shrink-0">
              {/* Turn counter */}
              {maxTurns > 0 && (
                <div className="flex flex-col items-center">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Turn</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {currentTurn}/{maxTurns}
                  </span>
                </div>
              )}

              {/* Tools executed */}
              <div className="flex flex-col items-center">
                <span className="text-xs text-gray-500 dark:text-gray-400">Tools</span>
                <span className="text-sm font-semibold text-gray-900 dark:text-white">
                  {completedTools}/{totalTools}
                </span>
              </div>

              {/* Events analyzed - always show */}
              <div className="flex flex-col items-center">
                <span className="text-xs text-gray-500 dark:text-gray-400">Events</span>
                <span className="text-sm font-semibold text-gray-900 dark:text-white">
                  {formatNumber(eventsAnalyzed)}
                </span>
              </div>

              {/* Timeline entries - always show */}
              <div className="flex flex-col items-center">
                <span className="text-xs text-gray-500 dark:text-gray-400">Timeline</span>
                <span className="text-sm font-semibold text-gray-900 dark:text-white">
                  {formatNumber(timelineEntriesAdded)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Expanded tool execution cards - fixed height with scroll */}
        {isExpanded && (
          <div className="border-t border-gray-200 dark:border-gray-700">
            <div
              className="overflow-y-auto p-3 space-y-2"
              style={{ height: '400px' }} // Fixed height to show ~5 tool cards
            >
              {toolExecutions.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    No tool executions yet
                  </p>
                </div>
              ) : (
                toolExecutions.map((tool, idx) => (
                  <ToolExecutionCard
                    key={`tool-${tool.execution_id}-${idx}`}
                    toolExecution={tool}
                    onReplicateQuery={onReplicateQuery}
                  />
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentExecutionContainer;
