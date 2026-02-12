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

  // Embedding state
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus | null>(null);
  const [hasSeenEmbeddingJobs, setHasSeenEmbeddingJobs] = useState(false);
  const [displayEmbeddingProgress, setDisplayEmbeddingProgress] = useState(0);
  const [displayEmbeddingCompleted, setDisplayEmbeddingCompleted] = useState(0);
  const [displayEmbeddingProcessing, setDisplayEmbeddingProcessing] = useState(0);
  const [hasEmbeddingConfig, setHasEmbeddingConfig] = useState(false);

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

      if (allComplete && fetchedJobs.length > 0 && onParsingComplete) {
        onParsingComplete();
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

  // Track parsing start time and elapsed seconds
  useEffect(() => {
    const parsingActive = parsingCounts.queued > 0 || parsingCounts.running > 0;

    if (parsingActive && parsingStartTime === null && !isLoading) {
      setParsingStartTime(Date.now());
      setElapsedSeconds(0);
    } else if (!parsingActive && parsingStartTime !== null) {
      setParsingStartTime(null);
      setElapsedSeconds(0);
      setEverHadQueued(false);
      setEverHadRunning(false);
      // Don't reset everHadCompleted - we want it to stay visible
      // setEverHadCompleted(false);
      setEverHadFailed(false);
    }
  }, [parsingCounts.queued, parsingCounts.running, parsingStartTime, isLoading]);

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
  // Show embedding section if: config exists AND (jobs active OR jobs have been seen)
  const embeddingActive = hasEmbeddingConfig && embeddingStatus && (!embeddingStatus.is_complete || (hasSeenEmbeddingJobs && embeddingStatus.progress_percent < 100));
  // Show embedding display when: embedding config exists AND (parsing is active OR embedding is active)
  // This avoids showing empty banner when nothing is happening
  const showEmbeddingDisplay = hasEmbeddingConfig && (parsingActive || embeddingActive);

  // Show banner only if parsing or embedding is actually active
  if (isLoading || (!parsingActive && !embeddingActive)) {
    return null;
  }

  const parsingProgress = parsingCounts.total > 0
    ? ((parsingCounts.completed + parsingCounts.failed) / parsingCounts.total) * 100
    : 0;

  const showDetailedStats = elapsedSeconds >= 15;

  // Determine primary status message
  let statusMessage = '';
  let statusIcon = null;
  
  if (parsingActive && embeddingActive) {
    statusMessage = `Processing ${totalParsingJobs} artifacts and generating embeddings`;
    statusIcon = <CogIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />;
  } else if (parsingActive) {
    statusMessage = showDetailedStats 
      ? "You can't send new questions until all artifacts finish parsing"
      : `Processing ${totalParsingJobs} artifacts... (${elapsedSeconds}s)`;
    statusIcon = <CogIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />;
  } else if (embeddingActive) {
    statusMessage = 'Augmented Chat mode will be available once embedding is complete';
    statusIcon = <SparklesIcon className="w-5 h-5 text-purple-600 dark:text-purple-400" />;
  }

  return (
    <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border-t border-blue-200 dark:border-blue-800 transition-all duration-300">
      <div className="max-w-4xl mx-auto">
        {/* Single unified header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {statusIcon}
            <span className="text-xs text-blue-600 dark:text-blue-400">
              {statusMessage}
            </span>
          </div>
          <div className="flex items-center gap-4">
            {parsingActive && (
              <span className="text-xs text-blue-700 dark:text-blue-300 font-mono">
                {parsingCounts.completed + parsingCounts.failed} / {totalParsingJobs} artifacts
              </span>
            )}
            {showEmbeddingDisplay && embeddingStatus && (
              <span className="text-xs text-blue-700 dark:text-blue-300">
                {displayEmbeddingCompleted.toLocaleString()}
                {displayEmbeddingProcessing > 0 && (
                  <span className="text-blue-500 dark:text-blue-400">
                    {' '}(+{displayEmbeddingProcessing.toLocaleString()})
                  </span>
                )}
                {' '}/ {embeddingStatus.events_total.toLocaleString()} events
              </span>
            )}
          </div>
        </div>

        {/* Combined progress bar */}
        <div className="space-y-2">
          {parsingActive && (
            <div className="w-full bg-blue-200 dark:bg-blue-900 rounded-full h-2">
              <div
                className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${parsingProgress}%` }}
              />
            </div>
          )}
          
          {showEmbeddingDisplay && (
            <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2 relative overflow-hidden">
              {embeddingStatus && displayEmbeddingProcessing > 0 && (
                <div
                  className="absolute top-0 left-0 h-2 bg-blue-400 dark:bg-blue-600 rounded-full transition-all duration-150"
                  style={{ 
                    width: `${((displayEmbeddingCompleted + displayEmbeddingProcessing) / (embeddingStatus.events_total || 1)) * 100}%`
                  }}
                ></div>
              )}
              <div
                className="absolute top-0 left-0 h-2 bg-blue-600 dark:bg-blue-400 rounded-full transition-all duration-150"
                style={{ width: `${displayEmbeddingProgress}%` }}
              ></div>
            </div>
          )}
        </div>

        {/* Detailed stats - show for parsing after 15 seconds */}
        {(parsingActive && showDetailedStats) && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 transition-all duration-300">
            {/* Queued - always show when detailed stats appear */}
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <ClockIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Queued</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">
                  {parsingCounts.queued}
                </div>
              </div>
            </div>

            {/* Parsing - always show when detailed stats appear */}
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <CogIcon className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Parsing</div>
                <div className="text-lg font-bold text-blue-600 dark:text-blue-400">
                  {parsingCounts.running}
                </div>
              </div>
            </div>

            {/* Completed - always show when detailed stats appear */}
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <CheckCircleIcon className="w-4 h-4 text-green-600 dark:text-green-400" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Completed</div>
                <div className="text-lg font-bold text-green-600 dark:text-green-400">
                  {parsingCounts.completed}
                </div>
              </div>
            </div>

            {/* Failed - only show if there are failures */}
            {everHadFailed && (
              <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
                <ExclamationCircleIcon className="w-4 h-4 text-red-600 dark:text-red-400" />
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Failed</div>
                  <div className="text-lg font-bold text-red-600 dark:text-red-400">
                    {parsingCounts.failed}
                  </div>
                </div>
              </div>
            )}

            {/* Embedding counter - show when embedding is configured */}
            {showEmbeddingDisplay && (
              <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
                <SparklesIcon className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Embedding</div>
                  <div className="text-lg font-bold text-purple-600 dark:text-purple-400">
                    {embeddingStatus ? Math.round(displayEmbeddingProgress) : 0}%
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {parsingActive && showDetailedStats && totalEvents > 0 && (
          <div className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-300 mt-2">
            <DocumentTextIcon className="w-4 h-4" />
            <span>
              <strong>{totalEvents.toLocaleString()}</strong> events parsed so far
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProcessingStatusBanner;
