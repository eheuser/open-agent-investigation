import { useEffect, useState } from 'react';
import axios from 'axios';

interface EmbeddingProgressBarProps {
  investigationId: string;
}

interface EmbeddingStatus {
  pending_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  total_jobs: number;
  events_pending: number;
  events_completed: number;
  events_total: number;
  progress_percent: number;
  is_complete: boolean;
}

export default function EmbeddingProgressBar({ investigationId }: EmbeddingProgressBarProps) {
  const [status, setStatus] = useState<EmbeddingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasSeenJobs, setHasSeenJobs] = useState(false);
  const [displayProgress, setDisplayProgress] = useState(0);
  const [displayCompleted, setDisplayCompleted] = useState(0);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await axios.get(
          `/api/v1/embeddings/status/${investigationId}`,
          {
            headers: { Authorization: `Bearer ${token}` }
          }
        );
        const data = response.data;
        //console.log('Embedding status:', data);
        setStatus(data);
        setIsLoading(false);
        
        // Track if we've ever seen jobs
        if (data.total_jobs > 0) {
          setHasSeenJobs(true);
        }
        
        // Initialize display values on first load
        if (displayProgress === 0 && data.progress_percent > 0) {
          setDisplayProgress(data.progress_percent);
          setDisplayCompleted(data.events_completed);
        }
      } catch (error) {
        console.error('Failed to fetch embedding status:', error);
        // Don't show error - just hide the component
        setIsLoading(false);
        setStatus({ 
          pending_jobs: 0, 
          running_jobs: 0, 
          completed_jobs: 0,
          total_jobs: 0,
          events_pending: 0,
          events_completed: 0,
          events_total: 0,
          progress_percent: 100,
          is_complete: true 
        });
      }
    };

    fetchStatus();

    // Poll every 2 seconds
    // Stop polling if: (1) we've seen jobs AND (2) they're now complete
    const interval = setInterval(() => {
      if (!hasSeenJobs || !status?.is_complete) {
        fetchStatus();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [investigationId, hasSeenJobs, status?.is_complete, displayProgress]);

  // Smooth easing animation for progress updates
  useEffect(() => {
    if (!status) return;

    const targetProgress = status.progress_percent;
    const targetCompleted = status.events_completed;

    // If target hasn't changed, don't animate
    if (targetProgress === displayProgress && targetCompleted === displayCompleted) {
      return;
    }

    // Animate progress over 1.5 seconds with easing
    const duration = 1500; // ms
    const steps = 30; // 30 frames
    const interval = duration / steps;
    let currentStep = 0;

    const progressDiff = targetProgress - displayProgress;
    const completedDiff = targetCompleted - displayCompleted;

    const timer = setInterval(() => {
      currentStep++;
      const progress = currentStep / steps;
      
      // Ease-out cubic: 1 - (1 - x)^3
      const eased = 1 - Math.pow(1 - progress, 3);

      setDisplayProgress(displayProgress + progressDiff * eased);
      setDisplayCompleted(Math.round(displayCompleted + completedDiff * eased));

      if (currentStep >= steps) {
        // Snap to final values
        setDisplayProgress(targetProgress);
        setDisplayCompleted(targetCompleted);
        clearInterval(timer);
      }
    }, interval);

    return () => clearInterval(timer);
  }, [status?.progress_percent, status?.events_completed, displayProgress, displayCompleted]);

  // Show if:
  // 1. Not loading AND
  // 2. Status exists AND
  // 3. Either (jobs are incomplete OR we've seen jobs and they just completed)
  const shouldShow = !isLoading && status && (!status.is_complete || (hasSeenJobs && status.progress_percent < 100));
  
  if (!shouldShow) {
    return null;
  }
  
  //console.log('EmbeddingProgressBar: Showing progress', status);

  return (
    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 mb-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <svg className="animate-spin h-4 w-4 text-blue-600 dark:text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
            Generating embeddings for RAG search
          </span>
        </div>
        <span className="text-xs text-blue-700 dark:text-blue-300">
          {displayCompleted.toLocaleString()} / {status.events_total.toLocaleString()} events
        </span>
      </div>
      
      <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
        <div 
          className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-150"
          style={{ width: `${displayProgress}%` }}
        ></div>
      </div>
      
      <div className="flex items-center justify-between mt-2">
        <p className="text-xs text-blue-600 dark:text-blue-400">
          Augmented Chat mode will be available once embedding is complete
        </p>
        <span className="text-xs font-medium text-blue-700 dark:text-blue-300">
          {Math.round(displayProgress)}%
        </span>
      </div>
    </div>
  );
}
