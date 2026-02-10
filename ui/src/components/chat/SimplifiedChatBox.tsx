/**
 * Simplified ChatBox component.
 * Uses single source of truth architecture with database as authority.
 */
import React, { useState, useRef, useEffect } from 'react';
import { useInvestigationChat, AgentEffort, RouterMode } from '../../hooks/useInvestigationChat';
import MessageRenderer from './MessageRenderer';
import ChatInput from './ChatInput';
import EmptyState from './EmptyState';
import LoadingState from './LoadingState';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import UploadModal from './UploadModal';
import ParsingStatusBanner from './ParsingStatusBanner';
import ConfigurationErrorModal from '../ConfigurationErrorModal';
import { useLLMConfig } from '../../hooks/useLLMConfig';
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';

interface SimplifiedChatBoxProps {
  investigationId: string;
  onGraphUpdated?: () => void;
  onReplicateQuery?: (queryParams: any) => void;
}

const SimplifiedChatBox: React.FC<SimplifiedChatBoxProps> = ({ investigationId, onGraphUpdated, onReplicateQuery }) => {
  const [input, setInput] = useState('');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [effort, setEffort] = useState<AgentEffort>('medium');
  const [mode, setMode] = useState<RouterMode>('auto');
  const [continuingJobId, setContinuingJobId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const [showConfigError, setShowConfigError] = useState(false);
  const [embeddingInProgress, setEmbeddingInProgress] = useState(false);

  // Floating search state
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<string[]>([]);
  const [currentResultIndex, setCurrentResultIndex] = useState(0);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const { ws, isConnected } = useWebSocketContext();
  const { checkConfig } = useLLMConfig();
  const {
    messages,
    isLoading,
    investigationState,
    parsingLocked,
    investigationChoices,
    sendMessage,
    deleteMessage,
    editMessage,
    selectChoice,
    dismissChoices,
  } = useInvestigationChat(investigationId);

  // Check embedding status periodically
  useEffect(() => {
    const checkEmbeddingStatus = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`/api/v1/embeddings/status/${investigationId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const status = await response.json();
          setEmbeddingInProgress(!status.is_complete);
        }
      } catch (error) {
        console.error('Failed to check embedding status:', error);
      }
    };

    checkEmbeddingStatus();
    const interval = setInterval(checkEmbeddingStatus, 3000);
    return () => clearInterval(interval);
  }, [investigationId]);

  // Check for LLM configuration errors in messages
  useEffect(() => {
    const hasConfigError = messages.some(msg =>
      msg.message_type === 'error' &&
      msg.content &&
      msg.content.toLowerCase().includes('no active llm configuration')
    );

    if (hasConfigError) {
      setShowConfigError(true);
    }
  }, [messages]);

  // Track scroll position to determine if user has scrolled up
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      // Consider user at bottom if within 150px of bottom
      // This gives them more freedom to scroll up without being yanked back
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      const isNearBottom = distanceFromBottom < 150;
      setShouldAutoScroll(isNearBottom);
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (!messagesEndRef.current || !messagesContainerRef.current) return;

    // Only auto-scroll if user is near the bottom
    // Don't force scroll if user has scrolled up to read previous messages
    if (shouldAutoScroll) {
      // Use requestAnimationFrame to ensure DOM has updated
      requestAnimationFrame(() => {
        // Double RAF to ensure layout is complete
        requestAnimationFrame(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        });
      });
    }
  }, [messages, shouldAutoScroll]);

  const handleSend = async () => {
    if (!input.trim() || investigationState === 'running' || !isConnected || parsingLocked) return;

    // Check for LLM config before sending
    const isValid = await checkConfig();
    if (!isValid) {
      setShowConfigError(true);
      return;
    }

    const messageText = input;
    setInput('');

    await sendMessage(messageText, effort, mode);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleStopAgent = () => {
    if (!ws || !isConnected) return;

    // Find the current job ID from the latest agent message
    const latestAgentMessage = [...messages]
      .reverse()
      .find(m => m.role === 'assistant' && m.metadata?.job_id);

    if (latestAgentMessage?.metadata?.job_id) {
      ws.send(JSON.stringify({
        type: 'stop_agent',
        job_id: latestAgentMessage.metadata.job_id,
      }));
    }
  };

  const handleContinueInvestigation = async (jobId: number, effort: string) => {
    if (!isConnected) return;

    // Immediately hide the banner by tracking the continuing job
    setContinuingJobId(jobId);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/v1/chat/continue/${jobId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ effort }),
      });

      if (!response.ok) {
        throw new Error('Failed to continue investigation');
        setContinuingJobId(null);
      }

      const data = await response.json();
      //console.log('Investigation continued:', data);

      // The API will broadcast message_updated and job_continuing via WebSocket
      // which will trigger the UI to update automatically
      // Keep continuingJobId set until we get the update
    } catch (error) {
      console.error('Failed to continue investigation:', error);
      setContinuingJobId(null);
      // TODO: Show error toast
    }
  };

  const isAgentRunning = investigationState === 'running';

  // Search functionality - find all <mark> elements
  useEffect(() => {
    if (!searchQuery) {
      setSearchResults([]);
      setCurrentResultIndex(0);
      // Remove all search highlights
      const container = messagesContainerRef.current;
      if (container) {
        container.querySelectorAll('mark.search-current').forEach(el => {
          el.classList.remove('search-current');
        });
      }
      return;
    }

    // Wait for DOM to update with new mark elements
    setTimeout(() => {
      const container = messagesContainerRef.current;
      if (!container) return;

      const markElements = container.querySelectorAll('mark[data-search-id]');
      const results: string[] = [];

      markElements.forEach((mark) => {
        const searchId = mark.getAttribute('data-search-id');
        if (searchId) {
          results.push(searchId);
        }
      });

      //console.log(`Found ${results.length} search results`);
      setSearchResults(results);
      setCurrentResultIndex(0);

      // Scroll to first result
      if (results.length > 0) {
        scrollToSearchResult(results[0]);
      }
    }, 100);
  }, [searchQuery, messages]);

  // Keyboard shortcut for search (Ctrl+F or Cmd+F)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        setShowSearch(true);
        setTimeout(() => searchInputRef.current?.focus(), 100);
      }
      if (e.key === 'Escape' && showSearch) {
        setShowSearch(false);
        setSearchQuery('');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showSearch]);

  const scrollToSearchResult = (searchId: string) => {
    const container = messagesContainerRef.current;
    if (!container) {
      //console.log('No container ref');
      return;
    }

    // Find the specific mark element by its search ID
    const targetElement = container.querySelector(`mark[data-search-id="${searchId}"]`) as HTMLElement;

    if (targetElement) {
      //console.log('Scrolling to search result:', searchId);

      // Remove previous highlight
      const previousHighlight = container.querySelector('mark.search-current');
      if (previousHighlight) {
        previousHighlight.classList.remove('search-current');
      }

      // Add current highlight
      targetElement.classList.add('search-current');

      // Scroll into view
      targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      //console.log('Could not find mark element with search ID:', searchId);
    }
  };

  const scrollToResult = (direction: 'next' | 'prev') => {
    if (searchResults.length === 0) return;

    let newIndex = currentResultIndex;
    if (direction === 'next') {
      newIndex = currentResultIndex + 1;
      if (newIndex >= searchResults.length) {
        newIndex = 0; // Wrap to start
      }
    } else {
      newIndex = currentResultIndex - 1;
      if (newIndex < 0) {
        newIndex = searchResults.length - 1; // Wrap to end
      }
    }

    setCurrentResultIndex(newIndex);
    scrollToSearchResult(searchResults[newIndex]);
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900 relative">
      {/* Configuration Error Modal */}
      <ConfigurationErrorModal
        isOpen={showConfigError}
        onClose={() => setShowConfigError(false)}
        title="LLM Configuration Required"
        message="You must configure an LLM provider before using the chat functionality. All natural language processing requires LLM capabilities."
        showSettingsButton={true}
      />

      {/* Upload Modal */}
      {showUploadModal && (
        <UploadModal
          investigationId={investigationId}
          onClose={() => setShowUploadModal(false)}
        />
      )}

      {/* Add global styles for search highlighting */}
      <style>{`
        mark.search-current {
          background-color: rgb(249 115 22) !important; /* orange-500 */
          outline: 2px solid rgb(249 115 22);
          outline-offset: 2px;
        }
        .dark mark.search-current {
          background-color: rgb(234 88 12) !important; /* orange-600 */
          outline: 2px solid rgb(234 88 12);
        }
      `}</style>

      {/* Floating Search Box */}
      {showSearch && (
        <div className="absolute top-4 right-4 z-50 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 p-3 w-80">
          <div className="flex items-center gap-2 mb-2">
            <MagnifyingGlassIcon className="w-4 h-4 text-gray-400" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  scrollToResult('next');
                }
              }}
              placeholder="Search messages..."
              className="flex-1 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={() => {
                setShowSearch(false);
                setSearchQuery('');
              }}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
            >
              <XMarkIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            </button>
          </div>

          {searchQuery && (
            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
              <span>
                {searchResults.length > 0 ? (
                  <>
                    {currentResultIndex + 1} of {searchResults.length} results
                  </>
                ) : (
                  'No results'
                )}
              </span>
              {searchResults.length > 0 && (
                <div className="flex gap-1">
                  <button
                    onClick={() => scrollToResult('prev')}
                    className="p-1.5 border-2 border-blue-500 dark:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
                    title="Previous result"
                  >
                    <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </button>
                  <button
                    onClick={() => scrollToResult('next')}
                    className="p-1.5 border-2 border-blue-500 dark:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
                    title="Next result (Enter)"
                  >
                    <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Search Toggle Button */}
      {!showSearch && (
        <button
          onClick={() => setShowSearch(true)}
          className="absolute top-4 right-4 z-40 p-2 bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 transition-colors"
          title="Search messages (Ctrl+F)"
        >
          <MagnifyingGlassIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        </button>
      )}

      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-700"
      >
        {isLoading ? (
          <LoadingState />
        ) : messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="w-full flex justify-center py-6">
            <div className="w-full max-w-4xl px-4 space-y-6">
              {messages.map((msg, index) => {
                // Augment message with continuation state if this job is continuing
                const augmentedMsg = msg.metadata?.job_id === continuingJobId
                  ? {
                    ...msg,
                    metadata: {
                      ...msg.metadata,
                      is_continuing: true,
                      isWaitingForLLM: true,
                    }
                  }
                  : msg;

                return (
                  <div
                    key={msg.message_id}
                    data-message-index={index}
                  >
                    <MessageRenderer
                      message={augmentedMsg}
                      isStreaming={
                        !!(msg.metadata?.streaming_message_id &&
                          isAgentRunning &&
                          msg === messages[messages.length - 1])
                      }
                      onDelete={deleteMessage}
                      onEdit={editMessage}
                      onContinue={handleContinueInvestigation}
                      onReplicateQuery={onReplicateQuery}
                      searchQuery={searchQuery}
                    />
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </div>

      {/* Investigation Continuation Choices */}
      {investigationChoices.length > 0 && (
        <div className="px-4 py-4 bg-blue-50 dark:bg-blue-900/20 border-t border-blue-200 dark:border-blue-800">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                Continue Investigation?
              </h3>
              <button
                onClick={dismissChoices}
                className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200"
              >
                Dismiss
              </button>
            </div>
            <p className="text-xs text-blue-700 dark:text-blue-300 mb-3">
              The investigation reached its turn limit. Choose how to continue:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {investigationChoices.map((choice) => (
                <button
                  key={choice.choice_id}
                  onClick={() => selectChoice(choice.choice_id)}
                  className="p-3 bg-white dark:bg-gray-800 border border-blue-200 dark:border-blue-700 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors text-left"
                >
                  <div className="font-medium text-sm text-blue-900 dark:text-blue-100 mb-1">
                    {choice.title}
                  </div>
                  <div className="text-xs text-blue-700 dark:text-blue-300">
                    {choice.description}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Parsing Status Banner */}
      {parsingLocked && (
        <ParsingStatusBanner investigationId={investigationId} />
      )}

      {/* Input Area */}
      <ChatInput
        value={input}
        onChange={setInput}
        onSend={handleSend}
        onKeyPress={handleKeyPress}
        onStop={handleStopAgent}
        isConnected={isConnected}
        isAgentRunning={isAgentRunning}
        disabled={investigationState === 'running' || parsingLocked}
        parsingLocked={parsingLocked}
        embeddingInProgress={embeddingInProgress}
        effort={effort}
        onEffortChange={setEffort}
        mode={mode}
        onModeChange={setMode}
      />
    </div>
  );
};

export default SimplifiedChatBox;
