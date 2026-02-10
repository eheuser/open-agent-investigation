import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../services/api';

interface JobsContextType {
  activeJobsCount: number;
  hasRunningJobs: boolean;
  showJobs: boolean;
  setShowJobs: (show: boolean) => void;
}

const JobsContext = createContext<JobsContextType | undefined>(undefined);

export const useJobs = () => {
  const context = useContext(JobsContext);
  if (!context) {
    throw new Error('useJobs must be used within a JobsProvider');
  }
  return context;
};

interface JobsProviderProps {
  children: ReactNode;
}

export const JobsProvider: React.FC<JobsProviderProps> = ({ children }) => {
  const location = useLocation();

  // Extract investigation ID from URL path
  const investigationId = React.useMemo(() => {
    const match = location.pathname.match(/\/investigation\/([^/]+)/);
    return match ? match[1] : undefined;
  }, [location.pathname]);
  const [activeJobsCount, setActiveJobsCount] = useState<number>(0);
  const [hasRunningJobs, setHasRunningJobs] = useState<boolean>(false);
  const [showJobs, setShowJobs] = useState(false);

  // Reset jobs state when not on an investigation page
  useEffect(() => {
    if (!investigationId) {
      setActiveJobsCount(0);
      setHasRunningJobs(false);
      return;
    }

    // Fetch job counts
    const fetchJobCounts = async () => {
      try {
        const [parsingResponse, agentResponse] = await Promise.all([
          api.get(`/api/v1/jobs/parsing/investigation/${investigationId}`),
          api.get(`/api/v1/jobs/agent/investigation/${investigationId}`)
        ]);

        const parsingJobs = parsingResponse.data.jobs || [];
        const agentJobs = agentResponse.data.jobs || [];

        // Count active jobs (pending or running)
        const activeParsingJobs = parsingJobs.filter(
          (job: any) => job.status === 'pending' || job.status === 'running'
        ).length;
        const activeAgentJobs = agentJobs.filter(
          (job: any) => job.status === 'pending' || job.status === 'running'
        ).length;

        const totalActive = activeParsingJobs + activeAgentJobs;
        setActiveJobsCount(totalActive);
        setHasRunningJobs(totalActive > 0);
      } catch (err) {
        console.error('Failed to fetch job counts:', err);
      }
    };

    fetchJobCounts();

    // Poll job counts every 2 seconds
    const jobInterval = setInterval(fetchJobCounts, 2000);

    return () => {
      if (jobInterval) {
        clearInterval(jobInterval);
      }
    };
  }, [investigationId]);

  return (
    <JobsContext.Provider value={{ activeJobsCount, hasRunningJobs, showJobs, setShowJobs }}>
      {children}
    </JobsContext.Provider>
  );
};
