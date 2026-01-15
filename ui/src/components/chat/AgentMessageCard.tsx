/**
 * Agent message card component.
 * Renders agent thinking/analysis with markdown support.
 */
import React, { useState } from 'react';
import { ChatMessage, ToolExecution } from '../../hooks/useInvestigationChat';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ClipboardDocumentIcon, CheckIcon, TrashIcon, ChevronDownIcon, ChevronRightIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import ToolExecutionCard from './ToolExecutionCard';

interface AgentMessageCardProps {
  message: ChatMessage;
  isStreaming?: boolean;
  onDelete?: (messageId: number) => void;
  onContinue?: (jobId: number, effort: string) => void;
  onReplicateQuery?: (queryParams: any) => void;
  searchQuery?: string;
}

interface ToolExecutionDisplayProps {
  tool: ToolExecution;
  onReplicateQuery?: (queryParams: any) => void;
}

/**
 * Compact, expandable tool execution display.
 * Similar to Continue.dev style - shows summary by default, expandable for details.
 */
const ToolExecutionDisplay: React.FC<ToolExecutionDisplayProps> = ({ tool, onReplicateQuery }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const getStatusIcon = () => {
    switch (tool.status) {
      case 'executing':
        return (
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        );
      case 'completed':
        return <span className="text-green-500">✓</span>;
      case 'failed':
        return <span className="text-red-500">✗</span>;
      default:
        return null;
    }
  };

  // Extract result count from result
  const getResultCount = () => {
    if (!tool.result) return null;
    
    // Check for common result patterns
    if (typeof tool.result === 'object') {
      // Search results: { count: N, events: [...] }
      if ('count' in tool.result) {
        return tool.result.count;
      }
      // Array results
      if ('events' in tool.result && Array.isArray(tool.result.events)) {
        return tool.result.events.length;
      }
      // Top values: { top_values: [...] }
      if ('top_values' in tool.result && Array.isArray(tool.result.top_values)) {
        return tool.result.top_values.length;
      }
    }
    
    return null;
  };

  const resultCount = getResultCount();

  const hasDetails = tool.arguments || tool.result;

  const handleCopy = async () => {
    const data = {
      tool: tool.tool_name,
      display_name: tool.display_name,
      status: tool.status,
      ...(tool.arguments && { arguments: tool.arguments }),
      ...(tool.result && { result: tool.result }),
      ...(tool.result_summary && { result_summary: tool.result_summary }),
    };
    await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="text-xs border-l-2 border-gray-300 dark:border-gray-600 pl-3 py-1 group/tool relative">
      {/* Copy button - show on hover */}
      <button
        onClick={handleCopy}
        className="absolute -right-1 top-0 p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded opacity-0 group-hover/tool:opacity-100 transition-opacity"
        title="Copy tool execution data"
      >
        {copied ? (
          <CheckIcon className="w-3 h-3 text-green-600" />
        ) : (
          <ClipboardDocumentIcon className="w-3 h-3 text-gray-500" />
        )}
      </button>

      {/* Compact header - always visible */}
      <div
        className={`flex items-center gap-2 ${
          hasDetails ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 -ml-1 pl-1 pr-2 py-1 rounded' : ''
        }`}
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
      >
        {/* Expand/collapse icon */}
        {hasDetails && (
          <div className="flex-shrink-0">
            {isExpanded ? (
              <ChevronDownIcon className="w-3 h-3 text-gray-400" />
            ) : (
              <ChevronRightIcon className="w-3 h-3 text-gray-400" />
            )}
          </div>
        )}

        {/* Status icon */}
        <div className="flex-shrink-0">{getStatusIcon()}</div>

        {/* Tool name/description and progress */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="font-medium text-gray-700 dark:text-gray-300 truncate">
            {tool.display_name || tool.tool_name}
          </span>
                      {tool.execution_number !== null && tool.max_tools && (
              <span className="text-gray-500 dark:text-gray-500 flex-shrink-0">
                Turn {tool.execution_number}/{tool.max_tools}
              </span>
            )}
        </div>

        {/* Result count and summary - compact */}
        {!isExpanded && (
          <div className="flex items-center gap-2 flex-shrink min-w-0">
            {resultCount !== null && (
              <span className="text-blue-600 dark:text-blue-400 font-medium flex-shrink-0">
                {resultCount} {resultCount === 1 ? 'result' : 'results'}
              </span>
            )}
            {tool.result_summary && (
              <span className="text-gray-600 dark:text-gray-400 truncate">
                {tool.result_summary}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Expanded details */}
      {isExpanded && hasDetails && (
        <div className="mt-2 space-y-2 text-xs">
          {/* Result summary - full */}
          {tool.result_summary && (
            <div className="text-gray-700 dark:text-gray-300">
              {tool.result_summary}
            </div>
          )}

          {/* Arguments */}
          {tool.arguments && Object.keys(tool.arguments).length > 0 && (
            <div>
              <div className="text-gray-500 dark:text-gray-400 font-medium mb-1">Arguments:</div>
              <pre className="bg-gray-50 dark:bg-gray-900 rounded p-2 overflow-x-auto text-xs">
                <code className="text-gray-800 dark:text-gray-200">{JSON.stringify(tool.arguments, null, 2)}</code>
              </pre>
            </div>
          )}

          {/* Result */}
          {tool.result && (
            <div>
              <div className="text-gray-500 dark:text-gray-400 font-medium mb-1">Result:</div>
              <pre className="bg-gray-50 dark:bg-gray-900 rounded p-2 overflow-x-auto text-xs max-h-64 overflow-y-auto">
                <code className="text-gray-800 dark:text-gray-200">{JSON.stringify(tool.result, null, 2)}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};


const AgentMessageCard: React.FC<AgentMessageCardProps> = ({ message, isStreaming, onDelete, onContinue, onReplicateQuery, searchQuery }) => {
  // Helper to highlight search terms in text with unique IDs
  const highlightSearchText = (text: string) => {
    if (!searchQuery || !text) return text;
    const regex = new RegExp(`(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    let counter = 0;
    return text.replace(regex, (match) => {
      const id = `${message.message_id}-${counter++}`;
      return `<mark class="bg-yellow-200 dark:bg-yellow-700 px-0.5 rounded" data-search-id="${id}">${match}</mark>`;
    });
  };
  const [copied, setCopied] = useState(false);
  const [selectedEffort, setSelectedEffort] = useState<string>('medium');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const isWaiting = message.metadata?.isWaitingForLLM;
  const isCompleted = message.metadata?.agent_completed;
  const isIncomplete = message.metadata?.investigation_incomplete;
  const isContinuing = message.metadata?.is_continuing;
  const canContinue = message.metadata?.can_continue;
  const jobId = message.metadata?.job_id;
  const stats = message.metadata?.stats;

  // Prefer explicit tool_executions from database over metadata
  // This is the new architecture - tool executions are stored in a separate table
  const toolExecutions: ToolExecution[] = message.tool_executions || 
    // Fall back to legacy metadata for backwards compatibility
    (message.metadata?.tool_executions?.map((te, idx) => ({
      execution_id: idx,
      chat_message_id: message.message_id,
      tool_name: te.tool,
      display_name: te.display_name || te.tool,
      arguments: te.arguments || null,
      result: te.result || null,
      result_summary: te.result_summary || null,
      status: te.status,
      execution_number: te.execution_number || null,
      max_tools: te.max_tools || null,
      started_at: null,
      finished_at: null,
    })) || []);

  // Remove tool-exec placeholders and LLM artifacts from content
  let cleanContent = (message.content || '')
    .replace(/<tool-exec[^>]*><\/tool-exec>/g, '') // Self-closing tags
    .replace(/<tool-exec[^>]*>[\s\S]*?<\/tool-exec>/g, '') // Tags with content
    .replace(/final functions\.\w+[^\n]*/gi, '') // Remove "final functions.complete_investigation..." artifacts
    .replace(/\bfunctions\.\w+\([^)]*\)/gi, '') // Remove function call artifacts
    .replace(/Calling \w+/gi, '') // Remove "Calling complete_investigation" etc
    .replace(/```json[\s\S]*?```/g, '') // Remove JSON code blocks
    .replace(/```[\s\S]*?```/g, '') // Remove any other code blocks
    .replace(/json:"summary"[^\n]*/gi, '') // Remove JSON artifacts
    .replace(/\{[\s\S]*?"summary"[\s\S]*?\}/g, '') // Remove JSON blocks with summary
    .replace(/^:\s*/gm, '') // Remove standalone colons at start of lines
    .replace(/\s+:\s*$/gm, '') // Remove trailing colons with whitespace
    .replace(/\n{3,}/g, '\n\n') // Clean up excessive newlines
    .trim();
  
  // If content starts with a JSON block, remove it
  if (cleanContent.startsWith('{')) {
    const jsonEndIndex = cleanContent.indexOf('}');
    if (jsonEndIndex > 0) {
      cleanContent = cleanContent.substring(jsonEndIndex + 1).trim();
    }
  }

  // Show loading animation ONLY if:
  // 1. Message is streaming
  // 2. No content yet
  // 3. No tool executions yet
  const hasAnyContent = cleanContent && cleanContent.length > 0;
  const hasAnyTools = toolExecutions.length > 0;
  const showLoadingAnimation = isStreaming && !hasAnyContent && !hasAnyTools;

  // Build chronological event stream using explicit sequence from backend
  type ChronologicalEvent = 
    | { type: 'text'; content: string; sequence: number }
    | { type: 'tool'; tool: ToolExecution; sequence: number };

  // Clean up malformed markdown
  const cleanMarkdown = (text: string): string => {
    // First, normalize line breaks
    text = text.replace(/\r\n/g, '\n');
    
    // Fix unbalanced ** (bold) markers
    const boldMarkers = text.match(/\*\*/g);
    if (boldMarkers && boldMarkers.length % 2 !== 0) {
      // Odd number of ** markers - remove the last one to balance
      const lastIndex = text.lastIndexOf('**');
      text = text.substring(0, lastIndex) + text.substring(lastIndex + 2);
    }
    
    // Fix unbalanced single * (italic) markers
    // Split by ** first to avoid counting ** as two *
    const parts = text.split('**');
    for (let i = 0; i < parts.length; i += 2) {
      // Only check parts that aren't inside bold markers
      const singleStars = parts[i].match(/\*/g);
      if (singleStars && singleStars.length % 2 !== 0) {
        // Remove the last single *
        const lastIdx = parts[i].lastIndexOf('*');
        parts[i] = parts[i].substring(0, lastIdx) + parts[i].substring(lastIdx + 1);
      }
    }
    text = parts.join('**');
    
    // Remove standalone ** that aren't part of bold formatting
    text = text.replace(/\s\*\*\s/g, ' ');
    text = text.replace(/^\*\*\s/g, '');
    text = text.replace(/\s\*\*$/g, '');
    
    // Fix common markdown issues from LLMs
    // Remove ** at start/end of lines if unmatched
    text = text.replace(/^\*\*$/gm, '');
    
    // Ensure proper spacing around code blocks
    text = text.replace(/```\n*/g, '\n```\n');
    text = text.replace(/\n*```/g, '\n```\n');
    
    // Clean up excessive blank lines
    text = text.replace(/\n{4,}/g, '\n\n\n');
    
    return text.trim();
  };

  const buildEventStream = (): ChronologicalEvent[] => {
    // Use explicit event_sequence from metadata if available
    const eventSequence = message.metadata?.event_sequence;
    
    if (eventSequence && eventSequence.length > 0) {
      // Map event_sequence to ChronologicalEvent format
      const mappedEvents = eventSequence.map(event => {
        if (event.type === 'thinking') {
          const content = event.content || '';
          // Skip empty or whitespace-only content
          if (!content.trim()) {
            return null;
          }
          
          return {
            type: 'text' as const,
            content: cleanMarkdown(content),
            sequence: event.sequence,
          };
        } else {
          // Find the corresponding tool execution
          const tool = toolExecutions.find(t => t.execution_id === event.execution_id);
          if (tool) {
            // Merge event data with tool data (event data takes precedence for status/summary)
            return {
              type: 'tool' as const,
              tool: {
                ...tool,
                status: event.status || tool.status,
                result_summary: event.result_summary || tool.result_summary,
                finished_at: event.completed_at || tool.finished_at,
              },
              sequence: event.sequence,
            };
          }
          // Fallback: create a minimal tool object from event data
          return {
            type: 'tool' as const,
            tool: {
              execution_id: event.execution_id || 0,
              chat_message_id: message.message_id,
              tool_name: event.tool_name || 'unknown',
              display_name: event.display_name || event.tool_name || 'Unknown Tool',
              arguments: null,
              result: null,
              result_summary: event.result_summary || null,
              status: event.status || 'executing',
              execution_number: event.execution_number || null,
              max_tools: event.max_tools || null,
              started_at: event.timestamp || null,
              finished_at: event.completed_at || null,
            },
            sequence: event.sequence,
          };
        }
      }) as ChronologicalEvent[];
      
      // Filter out internal control tools and null events (Phase 1 artifacts)
      return mappedEvents.filter(event => {
        if (event === null) {
          return false;
        }
        if (event.type === 'tool') {
          const toolName = event.tool.tool_name;
          // Hide internal control flow tools
          return toolName !== 'skip_timeline_registration';
        }
        return true;
      });
    }
    
    // Fallback: legacy mode - use old interleaving logic
    const events: ChronologicalEvent[] = [];
    let content = message.content || '';
    
    // Remove the "Starting analysis..." prefix if present
    content = content.replace(/^Starting analysis\.\.\.\s*/i, '').trim();
    
    if (toolExecutions.length === 0 && !content) {
      // No tools and no content
      return events;
    }
    
    if (toolExecutions.length === 0) {
      // No tools, just return the text content
      if (content) {
        events.push({ type: 'text', content: cleanMarkdown(content), sequence: 0 });
      }
      return events;
    }
    
    // Strategy: Split content into paragraphs and interleave with tools
    const paragraphs = content.split(/\n\n+/).filter(p => p.trim());
    
    let sequence = 0;
    const maxLength = Math.max(paragraphs.length, toolExecutions.length);
    
    for (let i = 0; i < maxLength; i++) {
      // Add text paragraph if available
      if (i < paragraphs.length) {
        const text = paragraphs[i].trim();
        if (text) {
          events.push({ type: 'text', content: cleanMarkdown(text), sequence: sequence++ });
        }
      }
      
      // Add tool execution if available
      if (i < toolExecutions.length) {
        events.push({ type: 'tool', tool: toolExecutions[i], sequence: sequence++ });
      }
    }
    
    return events;
  };

  const eventStream = buildEventStream();

  const handleCopy = async () => {
    const textContent = message.content || '';
    await navigator.clipboard.writeText(textContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDeleteClick = () => {
    setShowDeleteModal(true);
  };

  const confirmDelete = () => {
    if (onDelete) {
      onDelete(message.message_id);
      setShowDeleteModal(false);
    }
  };

  const cancelDelete = () => {
    setShowDeleteModal(false);
  };

  return (
    <>
    <div className="flex justify-start group pr-12">
      <div className="w-full max-w-4xl bg-gray-100 dark:bg-gray-800 rounded-lg px-4 py-3 shadow-sm relative" style={{ minHeight: showLoadingAnimation ? '80px' : 'auto' }}>
        {/* Action buttons - show on hover */}
        <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleCopy}
            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
            title="Copy message"
          >
            {copied ? (
              <CheckIcon className="w-4 h-4 text-green-600" />
            ) : (
              <ClipboardDocumentIcon className="w-4 h-4 text-gray-500" />
            )}
          </button>
          {onDelete && (
            <button
              onClick={handleDeleteClick}
              className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
              title="Delete message"
            >
              <TrashIcon className="w-4 h-4 text-gray-500" />
            </button>
          )}
        </div>
        {/* Assistant header - cleaner, more chat-like */}
        <div className="flex items-center gap-2 mb-2 text-sm text-gray-600 dark:text-gray-400">
          <span className="font-medium">Assistant</span>
          {/* Show "Thinking" with bouncing dots when waiting for LLM */}
          {isWaiting && (
            <div className="flex items-center gap-1.5 ml-1">
              <span className="text-xs text-gray-500 dark:text-gray-400">Thinking</span>
              <div className="flex gap-0.5">
                <div className="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          )}
        </div>

        {/* Chronological event stream - interleaves thinking and tool executions */}
        {/* Always show if we have events, even when completed or starting */}
        {eventStream.length > 0 && (
          <div className="space-y-3">
            {eventStream.map((event) => {
              if (event.type === 'text') {
                // Apply highlighting to text content
                const highlightedContent = searchQuery ? highlightSearchText(event.content) : event.content;
                
                return (
                  <div key={`text-${event.sequence}`} className="prose prose-sm dark:prose-invert max-w-none prose-p:my-3 prose-p:leading-relaxed prose-headings:my-3 prose-ul:my-2 prose-ol:my-2 prose-li:my-1 prose-code:before:content-none prose-code:after:content-none">
                    {searchQuery ? (
                      <div dangerouslySetInnerHTML={{ __html: highlightedContent }} className="text-gray-800 dark:text-gray-200 leading-relaxed" />
                    ) : (
                      <ReactMarkdown 
                      remarkPlugins={[remarkGfm]}
                      components={{
                        // Ensure paragraphs render properly with better spacing
                        p: ({node, ...props}) => <p className="my-3 text-gray-800 dark:text-gray-200 leading-relaxed" {...props} />,
                        // Ensure strong (bold) renders with high contrast
                        strong: ({node, ...props}) => <strong className="font-semibold text-gray-900 dark:text-white" {...props} />,
                        // Ensure em (italic) renders properly  
                        em: ({node, ...props}) => <em className="italic text-gray-800 dark:text-gray-200" {...props} />,
                        // Ensure code blocks render with high contrast
                        code: ({node, className, children, ...props}: any) => {
                          const inline = !className?.includes('language-');
                          if (inline) {
                            return (
                              <code 
                                className="bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100 px-1.5 py-0.5 rounded font-mono text-sm font-medium"
                                {...props}
                              >
                                {children}
                              </code>
                            );
                          }
                          return (
                            <code 
                              className="block bg-gray-900 dark:bg-gray-950 text-gray-100 dark:text-gray-200 p-3 rounded font-mono text-sm overflow-x-auto my-2"
                              {...props}
                            >
                              {children}
                            </code>
                          );
                        },
                        // Ensure lists render properly
                        ul: ({node, ...props}) => <ul className="my-2 space-y-1" {...props} />,
                        ol: ({node, ...props}) => <ol className="my-2 space-y-1" {...props} />,
                      }}
                      >
                        {event.content}
                      </ReactMarkdown>
                    )}
                  </div>
                );
              } else {
                const tool = event.tool;
                return (
                  <ToolExecutionCard
                    key={`tool-${event.sequence}-${tool.execution_id}`}
                    toolExecution={tool}
                    onReplicateQuery={onReplicateQuery}
                  />
                );
              }
            })}
          </div>
        )}

        {/* Show stats when investigation is complete or incomplete */}
        {(isCompleted || isIncomplete) && stats && (
          <div className="mt-4 pt-3 border-t border-gray-300 dark:border-gray-600">
            <small className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400">
              <span>
                <span className="font-medium">{stats.events_analyzed ?? 0}</span> events analyzed
              </span>
              <span>
                <span className="font-medium">{stats.timeline_entries_created ?? 0}</span> timeline entries
              </span>
              <span>
                <span className="font-medium">{stats.turns_executed ?? 0}</span> turns
              </span>
            </small>
          </div>
        )}

        {/* Show continuation option when investigation is incomplete and not currently continuing */}
        {isIncomplete && !isContinuing && canContinue && jobId && onContinue && (
          <div className="mt-4 pt-3 border-t border-yellow-300 dark:border-yellow-600">
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <div className="text-sm font-medium text-yellow-800 dark:text-yellow-200 mb-1">
                  Investigation Incomplete
                </div>
                <div className="text-xs text-yellow-700 dark:text-yellow-300">
                  The investigation reached its turn limit. You can continue with additional turns.
                </div>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={selectedEffort}
                  onChange={(e) => setSelectedEffort(e.target.value)}
                  className="text-sm px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                >
                  <option value="low">Quick (+5 turns)</option>
                  <option value="medium">Standard (+10 turns)</option>
                  <option value="high">Thorough (+15 turns)</option>
                </select>
                <button
                  onClick={() => onContinue(jobId, selectedEffort)}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded transition-colors"
                >
                  Continue
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>

    {/* Delete Confirmation Modal */}
    {showDeleteModal && (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        {/* Backdrop */}
        <div 
          className="absolute inset-0 bg-black bg-opacity-50"
          onClick={cancelDelete}
        />
        
        {/* Modal */}
        <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Delete Message
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                Are you sure you want to delete this message? This action cannot be undone.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={cancelDelete}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDelete}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )}
    </>
  );
};

export default AgentMessageCard;
