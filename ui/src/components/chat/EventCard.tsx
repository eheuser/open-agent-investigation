/**
 * Event card component for displaying forensic events in chat.
 * Shows event metadata and expandable payload.
 */
import React, { useState } from 'react';
import { ChevronDownIcon, ChevronRightIcon, ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline';

interface EventCardProps {
  event: {
    event_id?: number;
    event_type?: string;
    timestamp?: string;
    artifact_id?: number;
    payload?: any;
    [key: string]: any;
  };
  // Optional: show as query result
  isQueryResult?: boolean;
}

const EventCard: React.FC<EventCardProps> = ({ event, isQueryResult = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(event, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Format timestamp
  const formatTimestamp = (ts: string | undefined) => {
    if (!ts) return 'Unknown';
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  // Get event type badge color
  const getEventTypeBadge = (eventType: string | undefined) => {
    if (!eventType) return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200';
    
    // Security events - red
    if (eventType.includes('security') || eventType.includes('4624') || eventType.includes('4625')) {
      return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200';
    }
    // Sysmon events - blue
    if (eventType.includes('sysmon') || eventType.includes('process')) {
      return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200';
    }
    // File system events - green
    if (eventType.includes('mft') || eventType.includes('file')) {
      return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200';
    }
    // Registry events - purple
    if (eventType.includes('registry') || eventType.includes('reg_')) {
      return 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200';
    }
    // Browser events - orange
    if (eventType.includes('browser') || eventType.includes('chrome') || eventType.includes('firefox')) {
      return 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200';
    }
    // Default - gray
    return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200';
  };

  // Extract key fields from payload for preview
  const getPreviewFields = () => {
    const payload = event.payload || event;
    const preview: string[] = [];
    
    // Common interesting fields
    const interestingFields = [
      'EventID', 'TargetUserName', 'SubjectUserName', 'ProcessName', 'Image',
      'CommandLine', 'FileName', 'FullPath', 'SourceIP', 'IpAddress',
      'WorkstationName', 'LogonType', 'Status', 'FailureReason'
    ];
    
    for (const field of interestingFields) {
      if (payload[field]) {
        preview.push(`${field}: ${payload[field]}`);
        if (preview.length >= 3) break; // Show max 3 fields
      }
    }
    
    return preview;
  };

  const previewFields = getPreviewFields();

  return (
    <div className={`border rounded-lg ${
      isQueryResult
        ? 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/10'
        : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
    }`}>
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-t-lg transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* Expand/collapse icon */}
          <div className="flex-shrink-0">
            {isExpanded ? (
              <ChevronDownIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
            ) : (
              <ChevronRightIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
            )}
          </div>

          {/* Event type badge */}
          <div className="flex-shrink-0">
            <span className={`px-2 py-1 rounded text-xs font-medium ${getEventTypeBadge(event.event_type)}`}>
              {event.event_type || 'unknown'}
            </span>
          </div>

          {/* Preview info */}
          <div className="flex-1 min-w-0">
            <div className="text-sm text-gray-900 dark:text-white font-medium truncate">
              {event.event_id ? `Event #${event.event_id}` : 'Event'}
            </div>
            {previewFields.length > 0 && !isExpanded && (
              <div className="text-xs text-gray-600 dark:text-gray-400 truncate">
                {previewFields[0]}
              </div>
            )}
          </div>

          {/* Timestamp */}
          <div className="flex-shrink-0 text-xs text-gray-500 dark:text-gray-400">
            {formatTimestamp(event.timestamp)}
          </div>
        </div>

        {/* Copy button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleCopy();
          }}
          className="ml-2 p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition-colors"
          title="Copy event data"
        >
          {copied ? (
            <CheckIcon className="w-4 h-4 text-green-600" />
          ) : (
            <ClipboardDocumentIcon className="w-4 h-4 text-gray-500" />
          )}
        </button>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 p-3">
          {/* Metadata */}
          <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
            {event.event_id && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Event ID:</span>
                <span className="ml-2 text-gray-900 dark:text-white font-medium">{event.event_id}</span>
              </div>
            )}
            {event.artifact_id && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Artifact ID:</span>
                <span className="ml-2 text-gray-900 dark:text-white font-medium">{event.artifact_id}</span>
              </div>
            )}
            {event.timestamp && (
              <div className="col-span-2">
                <span className="text-gray-500 dark:text-gray-400">Timestamp:</span>
                <span className="ml-2 text-gray-900 dark:text-white font-medium">{formatTimestamp(event.timestamp)}</span>
              </div>
            )}
          </div>

          {/* Payload */}
          <div>
            <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Payload:
            </div>
            <div className="bg-gray-50 dark:bg-gray-900 rounded p-2 overflow-x-auto max-h-96">
              <pre className="text-xs text-gray-800 dark:text-gray-200">
                {JSON.stringify(event.payload || event, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EventCard;
