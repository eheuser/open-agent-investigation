import { useState, useEffect, useCallback } from 'react';
import { 
  getInvestigations, 
  getInvestigation,
  createInvestigation as createInvestigationAPI,
  updateInvestigation as updateInvestigationAPI,
  deleteInvestigation as deleteInvestigationAPI,
  Investigation,
  InvestigationCreate,
  InvestigationUpdate
} from '../services/investigations';

/**
 * Hook for managing investigations list
 */
export const useInvestigations = () => {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadInvestigations = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getInvestigations();
      setInvestigations(data);
    } catch (err) {
      setError('Failed to load investigations');
      console.error('Failed to load investigations:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createInvestigation = useCallback(async (data: InvestigationCreate) => {
    try {
      const newInv = await createInvestigationAPI(data);
      setInvestigations(prev => [newInv, ...prev]);
      return newInv;
    } catch (err) {
      console.error('Failed to create investigation:', err);
      throw err;
    }
  }, []);

  const updateInvestigation = useCallback(async (id: string, data: InvestigationUpdate) => {
    try {
      const updated = await updateInvestigationAPI(id, data);
      setInvestigations(prev => 
        prev.map(inv => inv.investigation_id === id ? updated : inv)
      );
      return updated;
    } catch (err) {
      console.error('Failed to update investigation:', err);
      throw err;
    }
  }, []);

  const deleteInvestigation = useCallback(async (id: string) => {
    try {
      await deleteInvestigationAPI(id);
      setInvestigations(prev => prev.filter(inv => inv.investigation_id !== id));
    } catch (err) {
      console.error('Failed to delete investigation:', err);
      throw err;
    }
  }, []);

  useEffect(() => {
    loadInvestigations();
  }, [loadInvestigations]);

  return {
    investigations,
    isLoading,
    error,
    loadInvestigations,
    createInvestigation,
    updateInvestigation,
    deleteInvestigation,
  };
};

/**
 * Hook for managing a single investigation
 */
export const useInvestigation = (id: string | undefined) => {
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadInvestigation = useCallback(async () => {
    if (!id) return;
    
    setIsLoading(true);
    setError(null);
    try {
      const data = await getInvestigation(id);
      setInvestigation(data);
    } catch (err) {
      setError('Failed to load investigation');
      console.error('Failed to load investigation:', err);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadInvestigation();
  }, [loadInvestigation]);

  return {
    investigation,
    isLoading,
    error,
    reload: loadInvestigation,
  };
};
