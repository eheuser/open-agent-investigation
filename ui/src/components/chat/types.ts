export interface Message {
  id: string;
  message_id?: number;
  role: 'user' | 'assistant' | 'system' | 'tool';
  message_type?: MessageType;
  content: string;
  timestamp: Date;
  parent_message_id?: number;
  metadata?: MessageMetadata;
  tool_executions?: ToolExecution[];
  deleted_at?: string;
}

export type MessageType = 
  | 'question'
  | 'assistant_answer'
  | 'timeline_query'
  | 'agent_chat'
  | 'tool_execution'
  | 'summary'
  | 'error'
  | 'system';

export type AgentEffort = 'low' | 'medium' | 'high';

export interface ToolExecution {
  execution_id: number;
  chat_message_id: number;
  tool_name: string;
  display_name?: string;
  arguments?: Record<string, any>;
  result?: Record<string, any>;
  result_summary?: string;
  status: 'executing' | 'completed' | 'failed';
  execution_number?: number;
  max_tools?: number;
  started_at?: string;
  finished_at?: string;
}

export interface MessageMetadata {
  type?: string;
  streaming_message_id?: string;
  job_id?: number;
  isWaitingForLLM?: boolean;
  agent_completed?: boolean;
  stats?: {
    events_analyzed?: number;
    timeline_entries_created?: number;
    turns_executed?: number;
  };
  summary?: string;
  intent?: string;
  effort?: AgentEffort;
  // Legacy tool_executions in metadata (for backwards compat)
  tool_executions?: Array<{
    tool: string;
    display_name?: string;
    arguments?: Record<string, any>;
    status: 'executing' | 'completed' | 'failed';
    result?: any;
    result_summary?: string;
    execution_number?: number;
    max_tools?: number;
  }>;
}

export interface ClarificationRequest {
  policy_id: string;
  policy_title: string;
  missing_rules: Array<{
    name: string;
    description: string;
    type: string;
    options?: string[];
  }>;
}

export interface MutationPreview {
  mutation_id: string;
  confirmation_text: string;
  mutations: any;
  changes: {
    add_nodes: number;
    add_edges: number;
    update_nodes: number;
    delete_nodes: number;
    delete_edges: number;
  };
}

export interface ChatBoxProps {
  investigationId: string;
  onGraphUpdated?: () => void;
}

export interface InvestigationState {
  parsing_locked: boolean;
  active_job?: {
    job_id: number;
    policy_id: string;
    status: string;
  } | null;
}
