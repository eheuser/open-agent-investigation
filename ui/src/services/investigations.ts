import api from './api';

export interface Investigation {
  investigation_id: string;
  title: string;
  owner_user_id?: number;
  created_at?: string;
  updated_at?: string;
  status?: string;
}

export interface InvestigationCreate {
  title: string;
}

export interface InvestigationUpdate {
  title?: string;
  status?: string;
}

/**
 * Fetch all investigations for the current user
 */
export const getInvestigations = async (): Promise<Investigation[]> => {
  const response = await api.get('/api/v1/investigations/');
  return response.data;
};

/**
 * Fetch a single investigation by ID
 */
export const getInvestigation = async (id: string): Promise<Investigation> => {
  const response = await api.get(`/api/v1/investigations/${id}`);
  return response.data;
};

/**
 * Create a new investigation
 */
export const createInvestigation = async (data: InvestigationCreate): Promise<Investigation> => {
  try {
    const response = await api.post('/api/v1/investigations/', data);
    return response.data;
  } catch (error: any) {
    console.error('Create investigation error:', error);
    console.error('Error response:', error.response?.data);
    console.error('Error status:', error.response?.status);
    throw error;
  }
};

/**
 * Update an investigation
 * Note: Update endpoint may not be implemented yet in the API
 */
export const updateInvestigation = async (
  id: string,
  data: InvestigationUpdate
): Promise<Investigation> => {
  try {
    const response = await api.patch(`/api/v1/investigations/${id}`, data);
    return response.data;
  } catch (error: any) {
    console.error('Update investigation error:', error);
    console.error('Error response:', error.response?.data);
    console.error('Error status:', error.response?.status);
    throw error;
  }
};

/**
 * Delete an investigation
 */
export const deleteInvestigation = async (id: string): Promise<void> => {
  await api.delete(`/api/v1/investigations/${id}`);
};
