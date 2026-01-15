/**
 * Message renderer - switches on message_type for clean rendering.
 * No string parsing, no placeholder reconstruction.
 */
import React from 'react';
import { ChatMessage } from '../../hooks/useInvestigationChat';
import UserMessageCard from './UserMessageCard';
import AgentMessageCard from './AgentMessageCard';
import ToolExecutionCard from './ToolExecutionCard';
import SummaryCard from './SummaryCard';
import ErrorCard from './ErrorCard';

interface MessageRendererProps {
  message: ChatMessage;
  isStreaming?: boolean;
  onEdit?: (messageId: number, newContent: string) => void;
  onDelete?: (messageId: number) => void;
  onContinue?: (jobId: number, effort: string) => void;
  onReplicateQuery?: (queryParams: any) => void;
  searchQuery?: string;
}

const MessageRenderer: React.FC<MessageRendererProps> = ({ message, isStreaming, onEdit, onDelete, onContinue, onReplicateQuery, searchQuery }) => {
  // Helper to highlight search terms
  const highlightText = (text: string) => {
    if (!searchQuery || !text) return text;
    const regex = new RegExp(`(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return text.replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-700 px-0.5 rounded">$1</mark>');
  };
  // Infer message type for legacy messages
  let messageType = message.message_type;
  
  if (!messageType) {
    // Legacy message - infer type from role and metadata
    if (message.role === 'user') {
      messageType = 'question';
    } else if (message.role === 'assistant') {
      // Check if this is a summary message (new architecture)
      if (message.metadata?.type === 'agent_summary') {
        messageType = 'summary';
      }
      // Legacy: check for old completion flag - but DON'T render as summary anymore
      // The working message with event_sequence should be rendered as agent_message
      else if (message.metadata?.type === 'agent_completed' || message.metadata?.agent_completed) {
        // This is the working message that was marked complete - render as agent_message
        messageType = 'agent_message';
      } else {
        messageType = 'agent_message';
      }
    } else if (message.role === 'system') {
      // Don't render system messages (they're internal)
      return null;
    }
  }
  
  switch (messageType) {
    case 'question':
      return (
        <UserMessageCard
          message={message}
          onEdit={onEdit}
          onDelete={onDelete}
          searchQuery={searchQuery}
        />
      );

    case 'agent_message':
    case 'assistant_answer':
    case 'agent_chat':
    case 'timeline_query':
      return (
        <AgentMessageCard
          message={message}
          isStreaming={isStreaming}
          onDelete={onDelete}
          onContinue={onContinue}
          onReplicateQuery={onReplicateQuery}
          searchQuery={searchQuery}
        />
      );

    case 'tool_execution':
      return (
        <ToolExecutionCard
          message={message}
          onReplicateQuery={onReplicateQuery}
          searchQuery={searchQuery}
        />
      );

    case 'summary':
      return (
        <SummaryCard
          message={message}
        />
      );

    case 'error':
      return (
        <ErrorCard
          message={message}
        />
      );

    default:
      // Legacy messages without message_type - render as simple text
      return (
        <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">
            {message.role}
          </div>
          <div className="text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
            {message.content || '(no content)'}
          </div>
        </div>
      );
  }
};

export default MessageRenderer;
