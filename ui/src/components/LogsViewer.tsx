import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  MagnifyingGlassIcon, 
  XMarkIcon,
  ArrowsUpDownIcon,
  PauseIcon,
  PlayIcon,
  ArrowDownIcon,
  ClipboardDocumentIcon,
  ClipboardDocumentCheckIcon
} from '@heroicons/react/24/outline';

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  module: string;
  funcName: string;
  lineno: number;
}

interface LogsViewerProps {
  investigationId: string;
}

const LogsViewer: React.FC<LogsViewerProps> = ({ investigationId }) => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [levelFilter, setLevelFilter] = useState<string>('ALL');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [isPaused, setIsPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [copiedAll, setCopiedAll] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const MAX_LOGS = 1000;

  // Connect to SSE endpoint for log streaming
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const host = window.location.hostname;
    const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
    const sseUrl = `${protocol}//${host}:${port}/api/v1/logs/stream`;

    const eventSource = new EventSource(sseUrl);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      if (!isPaused) {
        try {
          const logEntry: LogEntry = JSON.parse(event.data);
          setLogs((prevLogs) => {
            const newLogs = [...prevLogs, logEntry];
            // Keep only last 1000 logs (circular buffer)
            if (newLogs.length > MAX_LOGS) {
              return newLogs.slice(-MAX_LOGS);
            }
            return newLogs;
          });
        } catch (error) {
          console.error('Failed to parse log entry:', error);
        }
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      // EventSource will automatically reconnect
    };

    return () => {
      eventSource.close();
    };
  }, [isPaused]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  useEffect(() => {
    const container = logsContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setAutoScroll(isAtBottom);
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Filter and sort logs
  const filteredLogs = useMemo(() => {
    let result = logs;

    // Filter by level
    if (levelFilter !== 'ALL') {
      result = result.filter((log) => log.level === levelFilter);
    }

    // Filter by search term
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(
        (log) =>
          log.message.toLowerCase().includes(term) ||
          log.logger.toLowerCase().includes(term) ||
          log.module.toLowerCase().includes(term)
      );
    }

    // Sort
    if (sortOrder === 'asc') {
      result = [...result].reverse();
    }

    return result;
  }, [logs, searchTerm, levelFilter, sortOrder]);

  const getLevelColor = (level: string): string => {
    switch (level) {
      case 'DEBUG':
        return 'text-gray-400 dark:text-gray-500';
      case 'INFO':
        return 'text-blue-400 dark:text-blue-300';
      case 'WARNING':
        return 'text-yellow-400 dark:text-yellow-300';
      case 'ERROR':
        return 'text-red-400 dark:text-red-300';
      case 'CRITICAL':
        return 'text-red-600 dark:text-red-500 font-bold';
      default:
        return 'text-gray-300 dark:text-gray-400';
    }
  };

  const getLevelBadgeColor = (level: string): string => {
    switch (level) {
      case 'DEBUG':
        return 'bg-gray-700 text-gray-300';
      case 'INFO':
        return 'bg-blue-700 text-blue-100';
      case 'WARNING':
        return 'bg-yellow-700 text-yellow-100';
      case 'ERROR':
        return 'bg-red-700 text-red-100';
      case 'CRITICAL':
        return 'bg-red-900 text-red-100';
      default:
        return 'bg-gray-700 text-gray-300';
    }
  };

  const scrollToBottom = () => {
    setAutoScroll(true);
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const copyLogToClipboard = async (log: LogEntry, index: number) => {
    const logText = `${log.timestamp} ${log.level.padEnd(8)} ${log.logger.padEnd(40)} ${log.message} ${log.module}:${log.lineno}`;
    try {
      await navigator.clipboard.writeText(logText);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch (error) {
      console.error('Failed to copy log:', error);
    }
  };

  const copyAllLogsToClipboard = async () => {
    const allLogsText = filteredLogs
      .map(log => `${log.timestamp} ${log.level.padEnd(8)} ${log.logger.padEnd(40)} ${log.message} ${log.module}:${log.lineno}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(allLogsText);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
    } catch (error) {
      console.error('Failed to copy all logs:', error);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        {/* Search */}
        <div className="flex-1 relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search logs..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-8 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Level Filter */}
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
        >
          <option value="ALL">All Levels</option>
          <option value="DEBUG">Debug</option>
          <option value="INFO">Info</option>
          <option value="WARNING">Warning</option>
          <option value="ERROR">Error</option>
          <option value="CRITICAL">Critical</option>
        </select>

        {/* Sort Order */}
        <button
          onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
          title={`Sort ${sortOrder === 'asc' ? 'newest first' : 'oldest first'}`}
        >
          <ArrowsUpDownIcon className="w-4 h-4" />
          {sortOrder === 'asc' ? 'Oldest' : 'Newest'}
        </button>

        {/* Pause/Resume */}
        <button
          onClick={() => setIsPaused(!isPaused)}
          className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            isPaused
              ? 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-200 border border-yellow-300 dark:border-yellow-700'
              : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-white border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
          }`}
          title={isPaused ? 'Resume streaming' : 'Pause streaming'}
        >
          {isPaused ? (
            <>
              <PlayIcon className="w-4 h-4" />
              Paused
            </>
          ) : (
            <>
              <PauseIcon className="w-4 h-4" />
              Live
            </>
          )}
        </button>

        {/* Copy All Button */}
        <button
          onClick={copyAllLogsToClipboard}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white transition-colors"
          title="Copy all visible logs to clipboard"
        >
          {copiedAll ? (
            <>
              <ClipboardDocumentCheckIcon className="w-4 h-4 text-green-500" />
              Copied!
            </>
          ) : (
            <>
              <ClipboardDocumentIcon className="w-4 h-4" />
              Copy All
            </>
          )}
        </button>

        {/* Log Count */}
        <div className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
          {filteredLogs.length.toLocaleString()} / {logs.length.toLocaleString()} logs
        </div>
      </div>

      {/* Logs Display */}
      <div
        ref={logsContainerRef}
        className="flex-1 overflow-y-auto font-mono text-xs bg-gray-900 dark:bg-black p-4 space-y-1"
      >
        {filteredLogs.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-600 py-8">
            {logs.length === 0 ? 'Waiting for logs...' : 'No logs match your filters'}
          </div>
        ) : (
          filteredLogs.map((log, index) => (
            <div
              key={`${log.timestamp}-${index}`}
              className="group flex gap-3 py-1 px-2 rounded hover:bg-gray-800 dark:hover:bg-gray-900 transition-colors"
            >
              {/* Timestamp */}
              <span className="text-gray-500 dark:text-gray-600 whitespace-nowrap">
                {new Date(log.timestamp).toLocaleTimeString('en-US', { 
                  hour12: false, 
                  hour: '2-digit', 
                  minute: '2-digit', 
                  second: '2-digit',
                  fractionalSecondDigits: 3
                })}
              </span>

              {/* Level Badge - Fixed width to prevent size changes */}
              <span
                className={`px-2 py-0.5 rounded text-xs font-semibold whitespace-nowrap w-20 text-center ${getLevelBadgeColor(
                  log.level
                )}`}
              >
                {log.level}
              </span>

              {/* Logger */}
              <span className="text-cyan-400 dark:text-cyan-500 whitespace-nowrap min-w-[200px]">
                {log.logger}
              </span>

              {/* Message */}
              <span className={`flex-1 ${getLevelColor(log.level)}`}>
                {log.message}
              </span>

              {/* Location */}
              <span className="text-gray-600 dark:text-gray-700 whitespace-nowrap text-xs">
                {log.module}:{log.lineno}
              </span>

              {/* Copy Button - Only visible on hover */}
              <button
                onClick={() => copyLogToClipboard(log, index)}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-700 dark:hover:bg-gray-800 rounded flex-shrink-0"
                title="Copy log to clipboard"
              >
                {copiedIndex === index ? (
                  <ClipboardDocumentCheckIcon className="w-4 h-4 text-green-400" />
                ) : (
                  <ClipboardDocumentIcon className="w-4 h-4 text-gray-400 hover:text-gray-200" />
                )}
              </button>
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>

      {/* Scroll to Bottom Button */}
      {!autoScroll && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-6 right-6 p-3 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
          title="Scroll to bottom"
        >
          <ArrowDownIcon className="w-5 h-5" />
        </button>
      )}
    </div>
  );
};

export default LogsViewer;
