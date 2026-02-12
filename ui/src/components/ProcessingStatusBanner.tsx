import React, { useEffect, useState } from 'react';
import {
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  CogIcon,
  DocumentTextIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import api from '../services/api';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import axios from 'axios';

interface ParsingJob {
  job_id: number;
  artifact_id: number;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

interface EmbeddingStatus {
  pending_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  total_jobs: number;
  events_pending: number;
  events_processing: number;
  events_completed: number;
  events_total: number;
  progress_percent: number;
  is_complete: boolean;
}

interface ProcessingStatusBannerProps {
  investigationId: string;
  onParsingComplete?: () => void;
}

interface StatusCounts {
  queued: number;
  running: number;
  completed: number;
  failed: number;
  total: number;
}

const ProcessingStatusBanner: React.FC<ProcessingStatusBannerProps> = ({
  investigationId,
  onParsingComplete,
}) => {
  // Parsing state
  const [parsingJobs, setParsingJobs] = useState<ParsingJob[]>([]);
  const [totalParsingJobs, setTotalParsingJobs] = useState<number>(0);
  const [parsingCounts, setParsingCounts] = useState<StatusCounts>({
    queued: 0,
    running: 0,
    completed: 0,
    failed: 0,
    total: 0,
  });
  const [totalEvents, setTotalEvents] = useState<number>(0);
  const [parsingStartTime, setParsingStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [everHadQueued, setEverHadQueued] = useState(false);
  const [everHadRunning, setEverHadRunning] = useState(false);
  const [everHadCompleted, setEverHadCompleted] = useState(false);
  const [everHadFailed, setEverHadFailed] = useState(false);
  const [waitingForEmbedding, setWaitingForEmbedding] = useState(false);

  // Embedding state
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus | null>(null);
  const [hasSeenEmbeddingJobs, setHasSeenEmbeddingJobs] = useState(false);
  const [displayEmbeddingProgress, setDisplayEmbeddingProgress] = useState(0);
  const [displayEmbeddingCompleted, setDisplayEmbeddingCompleted] = useState(0);
  const [displayEmbeddingProcessing, setDisplayEmbeddingProcessing] = useState(0);
  const [hasEmbeddingConfig, setHasEmbeddingConfig] = useState(false);
  const [waitingStartTime, setWaitingStartTime] = useState<number | null>(null);
  const [bannerEverShown, setBannerEverShown] = useState(false);

  // Shared state
  const [isLoading, setIsLoading] = useState(true);
  const { ws, isConnected } = useWebSocketContext();

  // Fetch parsing jobs
  const fetchParsingJobs = async () => {
    try {
      const response = await api.get(`/api/v1/jobs/parsing/investigation/${investigationId}?limit=10000`);
      const fetchedJobs: ParsingJob[] = response.data.jobs || [];
      const apiTotal = response.data.total || 0;

      setParsingJobs(fetchedJobs);
      setTotalParsingJobs(apiTotal);

      const counts: StatusCounts = {
        queued: 0,
        running: 0,
        completed: 0,
        failed: 0,
        total: apiTotal,
      };

      fetchedJobs.forEach((job) => {
        if (job.status === 'pending') counts.queued++;
        else if (job.status === 'running') counts.running++;
        else if (job.status === 'completed') counts.completed++;
        else if (job.status === 'failed') counts.failed++;
      });

      setParsingCounts(counts);

      // Track which boxes have ever been shown (sticky display)
      if (counts.queued > 0) setEverHadQueued(true);
      if (counts.running > 0) setEverHadRunning(true);
      // Always show Completed counter once parsing starts (even at 0)
      if (counts.total > 0) setEverHadCompleted(true);
      if (counts.failed > 0) setEverHadFailed(true);

      // Check if all jobs are complete
      const allComplete = fetchedJobs.every(
        (job) => job.status === 'completed' || job.status === 'failed'
      );

      if (allComplete && fetchedJobs.length > 0) {
        // Parsing just completed - wait for embedding jobs to be created
        if (hasEmbeddingConfig && !hasSeenEmbeddingJobs) {
          setWaitingForEmbedding(true);
          // Start waiting timer
          if (waitingStartTime === null) {
            setWaitingStartTime(Date.now());
          }
        }
        if (onParsingComplete) {
          onParsingComplete();
        }
      }

      setIsLoading(false);
    } catch (error) {
      console.error('Failed to fetch parsing jobs:', error);
      setIsLoading(false);
    }
  };

  // Check if embedding is configured
  const checkEmbeddingConfig = async () => {
    try {
      const response = await api.get('/api/v1/llm-config/active');
      const config = response.data;
      // Check if embedding model is configured
      const hasConfig = !!(config?.embedding_model_name);
      setHasEmbeddingConfig(hasConfig);
    } catch (error) {
      // No active config or error - assume no embedding configured
      setHasEmbeddingConfig(false);
    }
  };

  // Fetch embedding status
  const fetchEmbeddingStatus = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `/api/v1/embeddings/status/${investigationId}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      const data = response.data;
      setEmbeddingStatus(data);

      // Track if we've ever seen embedding jobs
      if (data.total_jobs > 0) {
        setHasSeenEmbeddingJobs(true);
        setWaitingForEmbedding(false);  // Jobs created, no longer waiting
        setWaitingStartTime(null);  // Clear waiting timer
      } else if (waitingForEmbedding && waitingStartTime) {
        // If we've been waiting for 5 seconds and still no jobs, stop waiting
        // This handles the case where all events already have embeddings
        const waitingDuration = (Date.now() - waitingStartTime) / 1000;
        if (waitingDuration > 5) {
          setWaitingForEmbedding(false);
          setWaitingStartTime(null);
        }
      }

      // Initialize display values on first load only
      // The animation effect will handle subsequent updates
      if (displayEmbeddingProgress === 0 && displayEmbeddingCompleted === 0 && data.progress_percent > 0) {
        setDisplayEmbeddingProgress(data.progress_percent);
        setDisplayEmbeddingCompleted(data.events_completed);
        setDisplayEmbeddingProcessing(data.events_processing || 0);
      }
    } catch (error) {
      console.error('Failed to fetch embedding status:', error);
      setEmbeddingStatus({
        pending_jobs: 0,
        running_jobs: 0,
        completed_jobs: 0,
        total_jobs: 0,
        events_pending: 0,
        events_processing: 0,
        events_completed: 0,
        events_total: 0,
        progress_percent: 100,
        is_complete: true
      });
    }
  };

  // Fetch total event count
  const fetchEventCount = async () => {
    try {
      const response = await api.get(
        `/api/v1/events/${investigationId}?limit=1&offset=0`
      );
      setTotalEvents(response.data.total || 0);
    } catch (error) {
      console.error('Failed to fetch event count:', error);
    }
  };

  // Initial fetch
  useEffect(() => {
    const initialize = async () => {
      await Promise.all([fetchParsingJobs(), fetchEmbeddingStatus(), checkEmbeddingConfig()]);
    };
    initialize();
  }, [investigationId]);

  // Track processing start time and elapsed seconds (for both parsing and embedding)
  useEffect(() => {
    const parsingActive = parsingCounts.queued > 0 || parsingCounts.running > 0;
    const embeddingActive = hasEmbeddingConfig && embeddingStatus && (!embeddingStatus.is_complete || (hasSeenEmbeddingJobs && embeddingStatus.progress_percent < 100));
    const anyProcessingActive = parsingActive || embeddingActive;

    // Start timer when any processing begins
    if (anyProcessingActive && parsingStartTime === null && !isLoading) {
      setParsingStartTime(Date.now());
      setElapsedSeconds(0);
    } 
    // Only reset timer when BOTH parsing AND embedding are complete
    else if (!anyProcessingActive && parsingStartTime !== null) {
      setParsingStartTime(null);
      setElapsedSeconds(0);
      setEverHadQueued(false);
      setEverHadRunning(false);
      setEverHadCompleted(false);
      setEverHadFailed(false);
    }
  }, [parsingCounts.queued, parsingCounts.running, parsingStartTime, isLoading, hasEmbeddingConfig, embeddingStatus?.is_complete, embeddingStatus?.progress_percent, hasSeenEmbeddingJobs]);

  // Update elapsed time every second
  useEffect(() => {
    if (parsingStartTime === null) return;

    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - parsingStartTime) / 1000);
      setElapsedSeconds(elapsed);
    }, 1000);

    return () => clearInterval(interval);
  }, [parsingStartTime]);

  // Smooth easing animation for embedding progress updates
  useEffect(() => {
    if (!embeddingStatus) return;

    const targetProgress = embeddingStatus.progress_percent;
    const targetCompleted = embeddingStatus.events_completed;
    const targetProcessing = embeddingStatus.events_processing || 0;

    // If target hasn't changed, don't animate
    if (targetProgress === displayEmbeddingProgress && targetCompleted === displayEmbeddingCompleted && targetProcessing === displayEmbeddingProcessing) {
      return;
    }

    // Animate progress over 800ms with easing
    const duration = 800;
    const steps = 20;
    const stepDuration = duration / steps;
    let currentStep = 0;

    const startProgress = displayEmbeddingProgress;
    const startCompleted = displayEmbeddingCompleted;
    const startProcessing = displayEmbeddingProcessing;
    
    const progressDiff = targetProgress - startProgress;
    const completedDiff = targetCompleted - startCompleted;
    const processingDiff = targetProcessing - startProcessing;

    const timer = setInterval(() => {
      currentStep++;
      const progress = currentStep / steps;
      const eased = 1 - Math.pow(1 - progress, 3);

      if (currentStep >= steps) {
        // Snap to final values
        setDisplayEmbeddingProgress(targetProgress);
        setDisplayEmbeddingCompleted(targetCompleted);
        setDisplayEmbeddingProcessing(targetProcessing);
        clearInterval(timer);
      } else {
        setDisplayEmbeddingProgress(startProgress + progressDiff * eased);
        setDisplayEmbeddingCompleted(Math.round(startCompleted + completedDiff * eased));
        setDisplayEmbeddingProcessing(Math.round(startProcessing + processingDiff * eased));
      }
    }, stepDuration);

    return () => clearInterval(timer);
  }, [embeddingStatus?.progress_percent, embeddingStatus?.events_completed, embeddingStatus?.events_processing]);

  // Listen for WebSocket updates
  useEffect(() => {
    if (!ws || !isConnected) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        if (
          data.type === 'events_inserted' ||
          data.type === 'parsing_complete' ||
          data.type === 'job_status_update'
        ) {
          fetchParsingJobs();
          if (elapsedSeconds >= 15) {
            fetchEventCount();
          }
        }
      } catch (error) {
        // Ignore parse errors
      }
    };

    ws.addEventListener('message', handleMessage);
    return () => ws.removeEventListener('message', handleMessage);
  }, [ws, isConnected, elapsedSeconds]);

  // Poll for updates continuously (not just when active)
  // This ensures the banner appears quickly after file upload
  useEffect(() => {
    const parsingActive = parsingCounts.queued > 0 || parsingCounts.running > 0;
    const embeddingActive = embeddingStatus && !embeddingStatus.is_complete;

    // Poll every second when active, every 2 seconds when idle (to catch new jobs quickly)
    const pollInterval = (parsingActive || embeddingActive) ? 1000 : 2000;

    const interval = setInterval(() => {
      fetchParsingJobs();
      
      if (parsingActive && elapsedSeconds >= 15) {
        fetchEventCount();
      }
      
      if (embeddingActive || !hasSeenEmbeddingJobs) {
        fetchEmbeddingStatus();
      }
    }, pollInterval);

    return () => clearInterval(interval);
  }, [parsingCounts.queued, parsingCounts.running, elapsedSeconds, embeddingStatus?.is_complete, hasSeenEmbeddingJobs]);

  const parsingActive = parsingCounts.queued > 0 || parsingCounts.running > 0;
  // Show embedding section if: config exists AND (jobs active OR jobs have been seen OR waiting)
  const embeddingActive = hasEmbeddingConfig && embeddingStatus && (!embeddingStatus.is_complete || (hasSeenEmbeddingJobs && embeddingStatus.progress_percent < 100));
  // Show embedding display when: embedding config exists AND (parsing active OR embedding active OR waiting)
  const showEmbeddingDisplay = hasEmbeddingConfig && (parsingActive || embeddingActive || waitingForEmbedding);
  
  // Track if banner has ever been shown (to maintain continuity)
  useEffect(() => {
    if (parsingActive || embeddingActive || waitingForEmbedding) {
      setBannerEverShown(true);
    }
  }, [parsingActive, embeddingActive, waitingForEmbedding]);
  
  // Show banner if it has been shown and hasn't been reset yet
  const showBanner = bannerEverShown;
  
  // Reset banner state when all processing is truly complete
  useEffect(() => {
    const allDone = !parsingActive && !embeddingActive && !waitingForEmbedding;
    
    if (allDone && bannerEverShown) {
      // Wait 2 seconds after everything completes before hiding
      const timeout = setTimeout(() => {
        setBannerEverShown(false);
      }, 2000);
      return () => clearTimeout(timeout);
    }
  }, [parsingActive, embeddingActive, waitingForEmbedding, bannerEverShown]);

  // Show banner only if there's activity or we're in the transition period
  if (isLoading || !showBanner) {
    return null;
  }

  const parsingProgress = parsingCounts.total > 0
    ? ((parsingCounts.completed + parsingCounts.failed) / parsingCounts.total) * 100
    : 0;

  // Determine primary status message
  let statusMessage = '';
  let statusIcon = null;
  
  if (parsingActive && embeddingActive) {
    statusMessage = "You can't send new questions until all artifacts finish parsing";
    statusIcon = <CogIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />;
  } else if (parsingActive) {
    statusMessage = "You can't send new questions until all artifacts finish parsing";
    statusIcon = <CogIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />;
  } else if (waitingForEmbedding) {
    statusMessage = 'Preparing embeddings...';
    statusIcon = <CogIcon className="w-5 h-5 text-purple-600 dark:text-purple-400 animate-spin" />;
  } else if (embeddingActive) {
    statusMessage = 'Augmented Chat mode will be available once embedding is complete';
    statusIcon = <SparklesIcon className="w-5 h-5 text-purple-600 dark:text-purple-400" />;
  }

  return (
    <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border-t border-blue-200 dark:border-blue-800">
      <div className="max-w-4xl mx-auto">
        {/* Header with status message */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {statusIcon}
            <span className="text-xs text-blue-600 dark:text-blue-400">
              {statusMessage}
            </span>
          </div>
          <div className="flex items-center gap-4">
            {(parsingCounts.total > 0) && (
              <span className="text-xs text-blue-700 dark:text-blue-300 font-mono">
                {parsingCounts.completed + parsingCounts.failed} / {totalParsingJobs} artifacts
              </span>
            )}
            {totalEvents > 0 && (
              <span className="text-xs text-blue-700 dark:text-blue-300">
                {totalEvents.toLocaleString()} events
              </span>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-blue-200 dark:bg-blue-900 rounded-full h-2 mb-3">
          <div
            className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${parsingProgress}%` }}
          />
        </div>

        {/* Stats boxes - always show */}
        <div className="grid grid-cols-4 gap-3">
          {/* Queued */}
          <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
            <ClockIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Queued</div>
              <div className="text-lg font-bold text-gray-900 dark:text-white">
                {parsingCounts.queued}
              </div>
            </div>
          </div>

          {/* Parsing */}
          <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
            <CogIcon className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin" />
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Parsing</div>
              <div className="text-lg font-bold text-blue-600 dark:text-blue-400">
                {parsingCounts.running}
              </div>
            </div>
          </div>

          {/* Completed */}
          <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
            <CheckCircleIcon className="w-4 h-4 text-green-600 dark:text-green-400" />
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Completed</div>
              <div className="text-lg font-bold text-green-600 dark:text-green-400">
                {parsingCounts.completed}
              </div>
            </div>
          </div>

          {/* Embedding */}
          <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
            <SparklesIcon className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Embedding</div>
              <div className="text-lg font-bold text-purple-600 dark:text-purple-400">
                {embeddingStatus ? `${displayEmbeddingCompleted.toLocaleString()} / ${embeddingStatus.events_total.toLocaleString()}` : '0 / 0'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProcessingStatusBanner;
