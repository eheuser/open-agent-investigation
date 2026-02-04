import React, { useEffect, useState } from 'react';
import {
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  CogIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import api from '../../services/api';
import { useWebSocketContext } from '../../contexts/WebSocketContext';

interface ParsingJob {
  job_id: number;
  artifact_id: number;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

interface ParsingStatusBannerProps {
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

const ParsingStatusBanner: React.FC<ParsingStatusBannerProps> = ({
  investigationId,
  onParsingComplete,
}) => {
  const [jobs, setJobs] = useState<ParsingJob[]>([]);
  const [totalJobs, setTotalJobs] = useState<number>(0); // Total from API (not limited to 100)
  const [statusCounts, setStatusCounts] = useState<StatusCounts>({
    queued: 0,
    running: 0,
    completed: 0,
    failed: 0,
    total: 0,
  });
  const [totalEvents, setTotalEvents] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [parsingStartTime, setParsingStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [everHadQueued, setEverHadQueued] = useState(false);
  const [everHadRunning, setEverHadRunning] = useState(false);
  const [everHadCompleted, setEverHadCompleted] = useState(false);
  const [everHadFailed, setEverHadFailed] = useState(false);
  const { ws, isConnected } = useWebSocketContext();

  // Fetch parsing jobs
  const fetchJobs = async () => {
    try {
      // Fetch with high limit to get all jobs (API default is 100)
      const response = await api.get(`/api/v1/jobs/parsing/investigation/${investigationId}?limit=10000`);
      const fetchedJobs: ParsingJob[] = response.data.jobs || [];
      const apiTotal = response.data.total || 0;
      
      setJobs(fetchedJobs);
      setTotalJobs(apiTotal);

      // Calculate status counts
      const counts: StatusCounts = {
        queued: 0,
        running: 0,
        completed: 0,
        failed: 0,
        total: fetchedJobs.length,
      };

      fetchedJobs.forEach((job) => {
        if (job.status === 'pending') counts.queued++;
        else if (job.status === 'running') counts.running++;
        else if (job.status === 'completed') counts.completed++;
        else if (job.status === 'failed') counts.failed++;
      });

      // Use API total instead of fetched count for accurate progress
      counts.total = apiTotal;
      
      setStatusCounts(counts);

      // Track which boxes have ever been shown (sticky display)
      if (counts.queued > 0) setEverHadQueued(true);
      if (counts.running > 0) setEverHadRunning(true);
      if (counts.completed > 0) setEverHadCompleted(true);
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
      await fetchJobs();
      // After initial fetch, check if we should start the timer
      // This will be handled by the next useEffect
    };
    initialize();
  }, [investigationId]);

  // Track parsing start time and elapsed seconds
  useEffect(() => {
    const parsingActive = statusCounts.queued > 0 || statusCounts.running > 0;
    
    if (parsingActive && parsingStartTime === null && !isLoading) {
      // Parsing just started (and initial load is complete)
      setParsingStartTime(Date.now());
      setElapsedSeconds(0);
    } else if (!parsingActive && parsingStartTime !== null) {
      // Parsing finished - reset sticky flags for next parsing session
      setParsingStartTime(null);
      setElapsedSeconds(0);
      setEverHadQueued(false);
      setEverHadRunning(false);
      setEverHadCompleted(false);
      setEverHadFailed(false);
    }
  }, [statusCounts.queued, statusCounts.running, parsingStartTime, isLoading]);

  // Update elapsed time every second
  useEffect(() => {
    if (parsingStartTime === null) return;

    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - parsingStartTime) / 1000);
      setElapsedSeconds(elapsed);
    }, 1000);

    return () => clearInterval(interval);
  }, [parsingStartTime]);

  // Listen for WebSocket updates
  useEffect(() => {
    if (!ws || !isConnected) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        // Refresh on parsing-related events
        if (
          data.type === 'events_inserted' ||
          data.type === 'parsing_complete' ||
          data.type === 'job_status_update'
        ) {
          fetchJobs();
          // Only fetch event count after 15 seconds
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

  // Poll for updates every 2 seconds while parsing is active
  useEffect(() => {
    const parsingActive = statusCounts.queued > 0 || statusCounts.running > 0;

    if (parsingActive) {
      const interval = setInterval(() => {
        fetchJobs();
        
        // Progressive reveal: only fetch additional data after 15 seconds
        if (elapsedSeconds >= 15) {
          fetchEventCount();
        }
      }, 2000);

      return () => clearInterval(interval);
    }
  }, [statusCounts.queued, statusCounts.running, elapsedSeconds]);

  const parsingActive = statusCounts.queued > 0 || statusCounts.running > 0;

  // Don't show banner if:
  // 1. Still loading initial data
  // 2. No parsing jobs active
  if (isLoading || !parsingActive) {
    return null;
  }

  // Calculate progress
  const parsingProgress = statusCounts.total > 0
    ? ((statusCounts.completed + statusCounts.failed) / statusCounts.total) * 100
    : 0;
  
  // Progressive reveal: only show detailed stats after 15 seconds
  const showDetailedStats = elapsedSeconds >= 15;

  return (
    <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border-t border-blue-200 dark:border-blue-800">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <CogIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
            <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-100">
              Processing Artifacts
            </h3>
          </div>
          <div className="text-right">
            <div className="text-xs text-blue-700 dark:text-blue-300 font-mono">
              {statusCounts.completed + statusCounts.failed} / {totalJobs}
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-blue-200 dark:bg-blue-900 rounded-full h-2 mb-3">
          <div
            className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${parsingProgress}%` }}
          />
        </div>

        {/* Status Grid - Only show after 15 seconds */}
        {showDetailedStats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          {/* Queued - sticky once shown */}
          {everHadQueued && (
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <ClockIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Queued</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">
                  {statusCounts.queued}
                </div>
              </div>
            </div>
          )}

          {/* Running - sticky once shown */}
          {everHadRunning && (
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <CogIcon className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Parsing</div>
                <div className="text-lg font-bold text-blue-600 dark:text-blue-400">
                  {statusCounts.running}
                </div>
              </div>
            </div>
          )}

          {/* Completed - sticky once shown */}
          {everHadCompleted && (
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <CheckCircleIcon className="w-4 h-4 text-green-600 dark:text-green-400" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Completed</div>
                <div className="text-lg font-bold text-green-600 dark:text-green-400">
                  {statusCounts.completed}
                </div>
              </div>
            </div>
          )}

          {/* Failed - sticky once shown */}
          {everHadFailed && (
            <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-blue-200 dark:border-blue-700">
              <ExclamationCircleIcon className="w-4 h-4 text-red-600 dark:text-red-400" />
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Failed</div>
                <div className="text-lg font-bold text-red-600 dark:text-red-400">
                  {statusCounts.failed}
                </div>
              </div>
            </div>
          )}
        </div>
        )}

        {/* Event Count - Show after 15 seconds */}
        {showDetailedStats && totalEvents > 0 && (
          <div className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-300 mb-2">
            <DocumentTextIcon className="w-4 h-4" />
            <span>
              <strong>{totalEvents.toLocaleString()}</strong> events parsed so far
            </span>
          </div>
        )}

        {/* Info Message */}
        <p className="text-xs text-blue-600 dark:text-blue-400 mt-2">
          {!showDetailedStats && `⏳ Processing artifacts... (${elapsedSeconds}s)`}
          {showDetailedStats && '⏳ You can\'t send new questions until all artifacts finish parsing.'}
        </p>
      </div>
    </div>
  );
};

export default ParsingStatusBanner;
