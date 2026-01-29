// ui/src/services/playbooks.ts
import api from './api';

export interface BasePlaybook {
  name: string;
  description: string;
  playbook: string;
  is_base: true;
}

export interface Playbook {
  playbook_id: number;
  user_id: number;
  name: string;
  description: string;
  playbook: string;
  is_enabled: boolean;
  is_base: false;
  created_at: string;
  updated_at: string;
}

export type AnyPlaybook = BasePlaybook | Playbook;

export function isBasePlaybook(playbook: AnyPlaybook): playbook is BasePlaybook {
  return playbook.is_base === true;
}

export function isUserPlaybook(playbook: AnyPlaybook): playbook is Playbook {
  return playbook.is_base === false;
}

export interface PlaybookListResponse {
  base_playbooks: BasePlaybook[];
  user_playbooks: Playbook[];
  total: number;
}

export interface InvestigationPlaybook {
  id: number;
  investigation_id: string;
  playbook_id: number;
  is_enabled: boolean;
  enabled_at: string;
  playbook: Playbook;
}

export const getPlaybooks = async (): Promise<PlaybookListResponse> => {
  const response = await api.get('/api/v1/playbooks/list');
  return response.data;
};

export const getUserPlaybooks = async (): Promise<Playbook[]> => {
  const response = await api.get('/api/v1/playbooks/user');
  return response.data;
};

export const getBasePlaybooks = async (): Promise<BasePlaybook[]> => {
  const response = await api.get('/api/v1/playbooks/base');
  return response.data;
};

export const createPlaybook = async (data: {
  name: string;
  description: string;
  playbook: string;
  is_enabled?: boolean;
}): Promise<Playbook> => {
  const response = await api.post('/api/v1/playbooks/create', data);
  return response.data;
};

export const updatePlaybook = async (
  id: number,
  data: {
    name?: string;
    description?: string;
    playbook?: string;
    is_enabled?: boolean;
  }
): Promise<Playbook> => {
  const response = await api.put(`/api/v1/playbooks/${id}`, data);
  return response.data;
};

export const deletePlaybook = async (id: number): Promise<void> => {
  await api.delete(`/api/v1/playbooks/${id}`);
};

export const clonePlaybook = async (sourceName: string): Promise<Playbook> => {
  const response = await api.post(`/api/v1/playbooks/clone/${sourceName}`);
  return response.data;
};

export const getInvestigationPlaybooks = async (investigationId: string): Promise<InvestigationPlaybook[]> => {
  const response = await api.get(`/api/v1/playbooks/investigation/${investigationId}`);
  return response.data;
};

export const enablePlaybookForInvestigation = async (
  investigationId: string,
  playbookId: number,
  isEnabled: boolean = true
): Promise<void> => {
  await api.post(`/api/v1/playbooks/investigation/${investigationId}/enable`, {
    playbook_id: playbookId,
    is_enabled: isEnabled,
  });
};

export const disablePlaybookForInvestigation = async (
  investigationId: string,
  playbookId: number
): Promise<void> => {
  await api.delete(`/api/v1/playbooks/investigation/${investigationId}/disable/${playbookId}`);
};
