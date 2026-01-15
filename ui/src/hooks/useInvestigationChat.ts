/**
 * Simplified chat hook - single source of truth architecture.
 * 
 * Database is authoritative, UI is a view layer, WebSocket for notifications only.
 * No complex state management, no race conditions, no duplicate messages.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import api from '../services/api';

export interface ToolExecution {
  execution_id: number;
  chat_message_id: number;
  tool_name: string;
  display_name: string | null;
  arguments: Record<string, any> | null;
  result: Record<string, any> | null;
  result_summary: string | null;
  status: 'executing' | 'completed' | 'failed';
  execution_number: number | null;
  max_tools: number | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ChatMessage {
  message_id: number;
  investigation_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  message_type: 'question' | 'assistant_answer' | 'agent_chat' | 'agent_message' | 'timeline_query' | 'tool_execution' | 'summary' | 'error' | 'system' | null;
  content: string | null;
  parent_message_id: number | null;
  metadata: {
    // Legacy type field
    type?: string;
    
    // For agent messages
    streaming_message_id?: string;
    job_id?: number;
    isWaitingForLLM?: boolean;
    agent_completed?: boolean;
    investigation_incomplete?: boolean;
    can_continue?: boolean;
    is_continuing?: boolean;
    continuation_job_id?: number;
    stats?: {
      events_analyzed?: number;
      timeline_entries_created?: number;
      turns_executed?: number;
    };
    summary?: string;
    effort?: 'low' | 'medium' | 'high';
    
    // Event sequence for chronological ordering
    event_sequence?: Array<{
      type: 'thinking' | 'tool_execution';
      sequence: number;
      content?: string;  // For thinking events
      execution_id?: number;  // For tool_execution events
      tool_name?: string;
      display_name?: string;
      execution_number?: number;
      max_tools?: number;
      status?: 'executing' | 'completed' | 'failed';
      result_summary?: string;
      timestamp?: string;
      completed_at?: string;
    }>;
    
    // Legacy tool executions in metadata (for backwards compat)
    tool_executions?: Array<{
      tool: string;
      display_name: string;
      arguments: Record<string, any>;
      status: 'executing' | 'completed' | 'failed';
      result?: any;
      result_summary?: string;
      execution_number?: number;
      max_tools?: number;
    }>;
    // Individual tool execution fields (legacy)
    tool_name?: string;
    tool_display_name?: string;
    tool_arguments?: Record<string, any>;
    tool_result?: any;
    tool_result_summary?: string;
    tool_status?: 'executing' | 'completed' | 'failed';
    execution_number?: number;
    max_tools?: number;
    
    // For summaries
    intent?: string;
  };
  // Explicit tool executions from database (preferred over metadata)
  tool_executions?: ToolExecution[];
  deleted_at: string | null;
  created_at: string;
}

export interface InvestigationState {
  state: 'idle' | 'running' | 'completed' | 'failed';
}

export interface InvestigationChoice {
  choice_id: number;
  title: string;
  description: string;
  rationale: string;
  suggested_effort: 'low' | 'medium' | 'high';
}

export type AgentEffort = 'low' | 'medium' | 'high';
export type RouterMode = 'auto' | 'agent' | 'timeline' | 'augmented';

interface UseInvestigationChatResult {
  messages: ChatMessage[];
  isLoading: boolean;
  investigationState: InvestigationState['state'];
  parsingLocked: boolean;
  investigationChoices: InvestigationChoice[];
  sendMessage: (text: string, effort?: AgentEffort, mode?: RouterMode) => Promise<void>;
  deleteMessage: (messageId: number) => Promise<void>;
  editMessage: (messageId: number, newContent: string) => Promise<void>;
  refreshMessages: () => Promise<void>;
  selectChoice: (choiceId: number) => Promise<void>;
  dismissChoices: () => void;
}

export const useInvestigationChat = (investigationId: string): UseInvestigationChatResult => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [investigationState, setInvestigationState] = useState<InvestigationState['state']>('idle');
  const [parsingLocked, setParsingLocked] = useState(false);
  const [investigationChoices, setInvestigationChoices] = useState<InvestigationChoice[]>([]);
  
  // Track the current investigation to reset state on change
  const currentInvestigationRef = useRef(investigationId);
  
  // WebSocket context
  const { subscribe, ws } = useWebSocketContext();

  /**
   * Load all messages from database.
   * This is the single source of truth.
   */
  const loadMessages = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) {
        setIsLoading(true);
      }
      const response = await api.get(`/api/v1/chat/messages/${investigationId}`);
      const newMessages = response.data.messages || [];
      const locked = response.data.parsing_locked || false;
      
      // Update parsing lock state
      setParsingLocked(locked);
      
      // Only update if messages actually changed (prevent flashing)
      setMessages(prev => {
        if (JSON.stringify(prev) === JSON.stringify(newMessages)) {
          return prev; // No change, keep same reference
        }
        return newMessages;
      });
    } catch (error) {
      console.error('Failed to load messages:', error);
      setMessages([]);
    } finally {
      if (showLoading) {
        setIsLoading(false);
      }
    }
  }, [investigationId]);

  /**
   * Fetch a single message by ID (after WebSocket notification).
   */
  const fetchMessage = useCallback(async (messageId: number): Promise<ChatMessage | null> => {
    try {
      const response = await api.get(`/api/v1/chat/messages/single/${messageId}`);
      return response.data;
    } catch (error) {
      console.error(`Failed to fetch message ${messageId}:`, error);
      return null;
    }
  }, []);

  /**
   * Send a user message.
   * Backend now creates messages immediately, so no optimistic updates needed.
   */
  const sendMessage = useCallback(async (text: string, effort: AgentEffort = 'medium', mode: RouterMode = 'auto') => {
    if (!text.trim() || !ws) return;
    
    // Check if parsing is locked
    if (parsingLocked) {
      console.warn('Cannot send message while parsing is in progress');
      return;
    }

    // Set investigation state to running immediately for UI feedback
    setInvestigationState('running');

    try {
      // Send via WebSocket with effort level and router mode
      // Backend will immediately create user message and thinking assistant message
      ws.send(JSON.stringify({
        type: 'question',
        text: text,
        effort: effort,
        router_mode: mode,
      }));
      
      // Backend broadcasts:
      // 1. user_message (user's question)
      // 2. message_created (assistant thinking message with isWaitingForLLM=true)
      // These will be handled by WebSocket subscription and trigger refreshMessages()
    } catch (error) {
      console.error('Failed to send message:', error);
      setInvestigationState('idle');
      // TODO: Show error toast
    }
  }, [investigationId, ws, parsingLocked]);

  /**
   * Soft delete a message.
   */
  const deleteMessage = useCallback(async (messageId: number) => {
    try {
      await api.patch(`/api/v1/chat/messages/${messageId}`, {
        deleted_at: new Date().toISOString(),
      });
      // Optimistic update - remove from local state
      setMessages(prev => prev.filter(m => m.message_id !== messageId));
    } catch (error) {
      console.error('Failed to delete message:', error);
      // Refresh to get actual state
      await loadMessages(false);
    }
  }, [loadMessages]);

  /**
   * Edit a message's content.
   */
  const editMessage = useCallback(async (messageId: number, newContent: string) => {
    try {
      await api.patch(`/api/v1/chat/messages/${messageId}`, {
        content: newContent,
      });
      // Optimistic update
      setMessages(prev => prev.map(m => 
        m.message_id === messageId ? { ...m, content: newContent } : m
      ));
    } catch (error) {
      console.error('Failed to edit message:', error);
      // Refresh to get actual state
      await loadMessages(false);
    }
  }, [loadMessages]);

  /**
   * Refresh messages from database (without showing loading state).
   */
  const refreshMessages = useCallback(async () => {
    await loadMessages(false); // Don't show loading during refresh
  }, [loadMessages]);

  /**
   * Select a continuation choice and start a new agent job.
   */
  const selectChoice = useCallback(async (choiceId: number) => {
    try {
      const response = await api.post(`/api/v1/investigations/${investigationId}/choices/${choiceId}/select`);
      console.log('Choice selected, new job created:', response.data);
      
      // Clear choices from UI
      setInvestigationChoices([]);
      
      // Refresh messages to show new agent job
      await refreshMessages();
      
      // Set state to running
      setInvestigationState('running');
    } catch (error) {
      console.error('Failed to select choice:', error);
      // TODO: Show error toast
    }
  }, [investigationId, refreshMessages]);

  /**
   * Dismiss continuation choices without selecting.
   */
  const dismissChoices = useCallback(() => {
    setInvestigationChoices([]);
  }, []);

  /**
   * Check if there's an active job running (for page refresh recovery).
   */
  const checkActiveJob = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/chat/active-job/${investigationId}`);
      const activeJob = response.data.active_job;
      
      if (activeJob && activeJob.status === 'running') {
        console.log('Active job detected:', activeJob);
        setInvestigationState('running');
        return true;
      }
      return false;
    } catch (error) {
      console.error('Failed to check active job:', error);
      return false;
    }
  }, [investigationId]);

  /**
   * Load messages on mount or investigation change.
   */
  useEffect(() => {
    if (currentInvestigationRef.current !== investigationId) {
      // Investigation changed - reset state
      currentInvestigationRef.current = investigationId;
      setMessages([]);
      setIsLoading(true);
      setInvestigationState('idle');
    }
    
    // Load messages and check for active job
    const init = async () => {
      await loadMessages(true); // Show loading on initial load
      await checkActiveJob(); // Restore agent running state if applicable
    };
    init();
  }, [investigationId, loadMessages, checkActiveJob]);

  /**
   * Subscribe to WebSocket notifications.
   */
  useEffect(() => {
    const unsubscribe = subscribe(async (notification: any) => {
      // Only handle notifications for this investigation
      if (notification.investigation_id && notification.investigation_id !== investigationId) {
        return;
      }

      switch (notification.type) {
        // New simplified notifications
        case 'message_created':
          // Fetch the new message and append (with deduplication)
          const newMessage = await fetchMessage(notification.message_id);
          if (newMessage) {
            setMessages(prev => {
              // Deduplicate: check if message already exists
              const exists = prev.some(m => m.message_id === newMessage.message_id);
              if (exists) {
                console.warn(`Duplicate message_created for message_id=${newMessage.message_id}, skipping`);
                return prev;
              }
              return [...prev, newMessage];
            });
          }
          break;

        case 'message_updated':
          // Fetch updated message and replace
          const updatedMessage = await fetchMessage(notification.message_id);
          if (updatedMessage) {
            setMessages(prev =>
              prev.map(m =>
                m.message_id === updatedMessage.message_id ? updatedMessage : m
              )
            );
          }
          break;

        case 'investigation_state_changed':
          setInvestigationState(notification.state);
          break;

        // Agent lifecycle notifications
        case 'agent_started':
          // Agent started - set running state immediately
          setInvestigationState('running');
          // Don't refresh - let message_created handle it to preserve temp messages
          break;

        case 'agent_thinking':
        case 'agent_step':
        case 'tool_executing':
        case 'tool_result':
        case 'llm_waiting':
        case 'llm_chunk':
        case 'agent_message':
        case 'turn_complete':
          // Agent is running, these are handled by message_updated
          setInvestigationState('running');
          // Don't refresh on every event - message_updated will handle it
          break;

        case 'agent_completed':
          // Agent completed - update state and refresh
          setInvestigationState('completed');
          await refreshMessages();
          // After a short delay, set to idle
          setTimeout(() => setInvestigationState('idle'), 1000);
          break;

        case 'investigation_incomplete':
          // Investigation incomplete - update state and refresh
          setInvestigationState('idle'); // Set to idle so user can continue
          await refreshMessages();
          break;

        case 'job_continuing':
          // Investigation is being continued - set to running and refresh
          setInvestigationState('running');
          await refreshMessages();
          break;

        case 'job_completed':
        case 'job_failed':
        case 'user_stopped':
        case 'agent_cancelled':
        case 'stop_acknowledged':
          // Job ended, refresh and update state
          setInvestigationState('idle');
          await refreshMessages();
          break;

        case 'safety_limit_reached':
        case 'llm_error':
          // Error occurred, set to failed state
          setInvestigationState('failed');
          await refreshMessages();
          // After a delay, set to idle so user can try again
          setTimeout(() => setInvestigationState('idle'), 3000);
          break;

        case 'user_message':
          // User sent a message, refresh
          await refreshMessages();
          break;

        case 'message_deleted':
          // Message was deleted, remove from local state
          setMessages(prev => prev.filter(m => m.message_id !== notification.message_id));
          break;

        case 'parsing_started':
          // Parsing started, set lock
          setParsingLocked(true);
          break;

        case 'parsing_complete':
          // Parsing finished, clear lock
          setParsingLocked(false);
          break;

        case 'timeline_updated':
          // Timeline was updated (auto-registration), trigger refresh
          // This will update the timeline tab counter
          console.log('Timeline updated:', notification.entries_added, 'entries added');
          // Note: The parent component should listen for this and refresh timeline counts
          break;

        case 'investigation_choices_available':
          // Investigation continuation choices are available
          console.log('Investigation choices available:', notification.choices);
          setInvestigationChoices(notification.choices || []);
          break;

        case 'connected':
          // WebSocket connected
          console.log('WebSocket connected');
          break;

        case 'error':
          console.error('WebSocket error:', notification.message);
          setInvestigationState('failed');
          break;

        default:
          // Unknown notification type - log for debugging
          console.debug('Unknown WebSocket notification:', notification.type);
          break;
      }
    });

    return unsubscribe;
  }, [investigationId, subscribe, fetchMessage, refreshMessages]);

  /**
   * Periodic refresh while agent is running (fallback).
   */
  useEffect(() => {
    if (investigationState !== 'running') return;

    const interval = setInterval(() => {
      refreshMessages();
    }, 3000); // Refresh every 3 seconds while running

    return () => clearInterval(interval);
  }, [investigationState, refreshMessages]);

  return {
    messages,
    isLoading,
    investigationState,
    parsingLocked,
    investigationChoices,
    sendMessage,
    deleteMessage,
    editMessage,
    refreshMessages,
    selectChoice,
    dismissChoices,
  };
};
