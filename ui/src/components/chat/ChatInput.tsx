import React, { useRef, useEffect, useState } from 'react';
import { PaperAirplaneIcon, PlusIcon, StopIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import { AgentEffort, RouterMode } from '../../hooks/useInvestigationChat';
import ConfigurationErrorModal from '../ConfigurationErrorModal';
import { useLLMConfig } from '../../hooks/useLLMConfig';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onAttach?: () => void;
  onStop?: () => void;
  onKeyPress?: (e: React.KeyboardEvent) => void;
  isConnected: boolean;
  isAgentRunning: boolean;
  disabled?: boolean;
  parsingLocked?: boolean;
  effort?: AgentEffort;
  onEffortChange?: (effort: AgentEffort) => void;
  mode?: RouterMode;
  onModeChange?: (mode: RouterMode) => void;
}

const effortLabels: Record<AgentEffort, { label: string; iterations: number }> = {
  low: { label: 'Quick', iterations: 3 },
  medium: { label: 'Standard', iterations: 6 },
  high: { label: 'Thorough', iterations: 9 },
};

const modeLabels: Record<RouterMode, { label: string; description: string }> = {
  auto: { label: 'Auto', description: 'Automatic routing based on query' },
  agent: { label: 'Agent', description: 'Always use investigation agent' },
  timeline: { label: 'Timeline', description: 'Timeline CRUD operations' },
  augmented: { label: 'Augmented Chat', description: 'RAG + LLM chat' },
};

const ChatInput: React.FC<ChatInputProps> = ({ 
  value, 
  onChange, 
  onSend, 
  onAttach,
  onStop,
  onKeyPress,
  isConnected,
  isAgentRunning,
  disabled = false,
  parsingLocked = false,
  effort = 'medium',
  onEffortChange,
  mode = 'auto',
  onModeChange,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { hasConfig, checkConfig } = useLLMConfig();
  const [showConfigError, setShowConfigError] = useState(false);

  const handleSendClick = async () => {
    // Check for LLM config before sending
    const isValid = await checkConfig();
    if (!isValid) {
      setShowConfigError(true);
      return;
    }
    onSend();
  };

  // Auto-resize the textarea as the user types
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      const maxHeight = 200;
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    }
  }, [value]);

  const handleKeyDown = async (e: React.KeyboardEvent) => {
    if (onKeyPress) {
      onKeyPress(e);
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // Check for LLM config before sending
      const isValid = await checkConfig();
      if (!isValid) {
        setShowConfigError(true);
        return;
      }
      onSend();
    }
  };

  return (
    <>
      <ConfigurationErrorModal
        isOpen={showConfigError}
        onClose={() => setShowConfigError(false)}
        title="LLM Configuration Required"
        message="You must configure an LLM provider before sending messages. All chat functionality requires LLM capabilities for processing natural language queries."
        showSettingsButton={true}
      />
      <div className="p-4">
      <div className="max-w-3xl mx-auto">
        {/* Connection Status */}
        {!isConnected && (
          <div className="mb-2 px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg text-sm text-yellow-800 dark:text-yellow-200">
            ⚠️ Connecting to chat server...
          </div>
        )}
        {/* Removed the "Agent is analyzing..." banner - status is shown in the message card itself */}
        <div className="relative flex items-center gap-2 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-3xl shadow-sm hover:shadow-md focus-within:shadow-md transition-all px-2 py-2">
          {/* Removed attachment button - users can drag/drop files onto the canvas */}

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            rows={1}
            disabled={isAgentRunning || disabled || parsingLocked}
            className="flex-1 bg-transparent py-3 px-2 resize-none focus:outline-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 max-h-[200px] overflow-hidden disabled:opacity-50 disabled:cursor-not-allowed"
          />

          {/* Send/Stop Button */}
          {isAgentRunning && onStop ? (
            <button
              onClick={onStop}
              className="flex-shrink-0 p-2.5 rounded-full bg-red-600 hover:bg-red-700 text-white transition-all"
              title="Stop agent"
            >
              <StopIcon className="w-6 h-6" />
            </button>
          ) : (
            <button
              onClick={handleSendClick}
              disabled={!value.trim() || !isConnected || isAgentRunning || parsingLocked}
              className={`flex-shrink-0 p-2.5 rounded-full transition-all ${
                value.trim() && isConnected && !isAgentRunning && !parsingLocked
                  ? 'bg-gray-200 dark:bg-gray-600 hover:bg-gray-300 dark:hover:bg-gray-500 text-gray-700 dark:text-gray-200'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
              }`}
              title={!isConnected ? 'Connecting...' : isAgentRunning ? 'Agent is running...' : parsingLocked ? 'Parsing artifacts...' : 'Send message'}
            >
              <PaperAirplaneIcon className="w-6 h-6" />
            </button>
          )}
        </div>
        
        {/* Helper Text and Controls */}
        <div className="flex items-center justify-between mt-2 px-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Press Enter to send, Shift+Enter for new line
          </p>
          
          <div className="flex items-center gap-4">
            {/* Mode Selector */}
            {onModeChange && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">Mode:</span>
                <div className="relative">
                  <select
                    value={mode}
                    onChange={(e) => onModeChange(e.target.value as RouterMode)}
                    disabled={isAgentRunning || parsingLocked}
                    className="appearance-none bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 pr-6 text-xs text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                    title={modeLabels[mode].description}
                  >
                    <option value="auto">{modeLabels.auto.label}</option>
                    <option value="agent">{modeLabels.agent.label}</option>
                    <option value="timeline">{modeLabels.timeline.label}</option>
                    <option value="augmented">{modeLabels.augmented.label}</option>
                  </select>
                  <ChevronDownIcon className="absolute right-1 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500 pointer-events-none" />
                </div>
              </div>
          )}
            
            {/* Effort Selector */}
            {onEffortChange && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">Effort:</span>
                <div className="relative">
                  <select
                    value={effort}
                    onChange={(e) => onEffortChange(e.target.value as AgentEffort)}
                    disabled={isAgentRunning || parsingLocked}
                    className="appearance-none bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 pr-6 text-xs text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                  >
                    <option value="low">{effortLabels.low.label} ({effortLabels.low.iterations} turns)</option>
                    <option value="medium">{effortLabels.medium.label} ({effortLabels.medium.iterations} turns)</option>
                    <option value="high">{effortLabels.high.label} ({effortLabels.high.iterations} turns)</option>
                  </select>
                  <ChevronDownIcon className="absolute right-1 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500 pointer-events-none" />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
    </>
  );
};

export default ChatInput;
