import React, { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import SimplifiedChatBox from '../components/chat/SimplifiedChatBox';
import TimelineViewer from '../components/TimelineViewer';
import EventsViewer from '../components/EventsViewer';
import ReportGenerator from '../components/ReportGenerator';
import JobsModal from '../components/JobsModal';
import UploadModal from '../components/chat/UploadModal';
import { useInvestigation } from '../hooks/useInvestigations';
import { useJobs } from '../contexts/JobsContext';
import { WebSocketProvider } from '../contexts/WebSocketContext';
import { useInvestigationCounts } from '../hooks/useInvestigationCounts';
import { 
  ClockIcon,
  DocumentTextIcon,
  ChatBubbleLeftRightIcon,
  TableCellsIcon,
  DocumentChartBarIcon
} from '@heroicons/react/24/outline';



type TabType = 'chat' | 'events' | 'timeline' | 'report';

const InvestigationDetailContent: React.FC<{ investigationId: string }> = ({ investigationId }) => {
  const { investigation, isLoading, error } = useInvestigation(investigationId);
  const { showJobs, setShowJobs } = useJobs();
  const [activeTab, setActiveTab] = useState<TabType>('chat');
  const [timelineKey, setTimelineKey] = useState(0); // Key to force timeline refresh
  const [timelineNeedsRefresh, setTimelineNeedsRefresh] = useState(false);
  const [chatKey] = useState(() => `chat-${investigationId}`); // Stable key per investigation
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
  const [eventsTabFlash, setEventsTabFlash] = useState(false);
  const [replicatedQuery, setReplicatedQuery] = useState<any>(null);
  // Use the centralized WebSocket for counts
  const { eventCount, timelineEntryCount, timelineCountChanged } = useInvestigationCounts({
    investigationId,
    activeTab,
    onTimelineRefresh: () => {
      if (activeTab === 'timeline') {
        // If timeline tab is active, refresh immediately
        setTimelineKey(prev => prev + 1);
      } else {
        // If timeline tab is not active, mark for refresh when user switches to it
        setTimelineNeedsRefresh(true);
      }
    },
  });
  
  // Handle query replication from chat
  const handleReplicateQuery = useCallback((queryParams: any) => {
    // Set the replicated query
    setReplicatedQuery(queryParams);
    
    // Switch to Events tab
    setActiveTab('events');
    
    // Trigger flash animation
    setEventsTabFlash(true);
    setTimeout(() => setEventsTabFlash(false), 1000);
  }, []);

  // Global drag and drop handlers
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDraggingOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set to false if we're leaving the dropzone itself
    if (e.currentTarget === e.target) {
      setIsDraggingOver(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      setDroppedFiles(files);
      setShowUploadModal(true);
    }
  }, []);



  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-gray-600 dark:text-gray-400">Loading investigation...</p>
        </div>
      </div>
    );
  }

  if (error || !investigation) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400">{error || 'Investigation not found'}</p>
        </div>
      </div>
    );
  }

  return (
    <div 
      className="flex flex-col h-full relative"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Global drag overlay */}
      {isDraggingOver && (
        <div className="absolute inset-0 bg-blue-500 bg-opacity-10 border-4 border-dashed border-blue-500 dark:border-blue-400 z-40 flex items-center justify-center pointer-events-none">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-8 border-2 border-blue-500 dark:border-blue-400">
            <div className="text-center">
              <DocumentTextIcon className="w-16 h-16 mx-auto mb-4 text-blue-500 dark:text-blue-400" />
              <p className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Drop files to upload</p>
              <p className="text-sm text-gray-600 dark:text-gray-400">Supported: EVTX, Registry, MFT, Prefetch, LNK</p>
            </div>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <UploadModal
          investigationId={investigationId}
          initialFiles={droppedFiles.length > 0 ? droppedFiles : undefined}
          onClose={() => {
            setShowUploadModal(false);
            setDroppedFiles([]);
          }}
        />
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Tabs - aligned with sidebar header */}
        <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 relative" style={{ height: '52px' }}>
          <div className="px-3 flex items-center gap-0 h-full">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-2 px-4 text-sm font-medium transition-colors relative ${
              activeTab === 'chat'
                ? 'text-blue-600 dark:text-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            <ChatBubbleLeftRightIcon className="w-4 h-4" />
            Chat
            {activeTab === 'chat' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 dark:bg-blue-400" style={{ bottom: '-1px' }} />
            )}
          </button>
          
          <button
            onClick={() => setActiveTab('events')}
            className={`flex items-center gap-2 px-4 text-sm font-medium transition-colors relative ${
              activeTab === 'events'
                ? 'text-blue-600 dark:text-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            <TableCellsIcon className="w-4 h-4" />
            Events
            {eventCount > 0 && (
              <span className={`inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold leading-none rounded-full transition-all duration-500 ${
                eventsTabFlash
                  ? 'text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/40 ring-2 ring-blue-400 dark:ring-blue-500'
                  : 'text-gray-700 dark:text-gray-200 bg-gray-200 dark:bg-gray-700'
              }`}>
                {eventCount.toLocaleString()}
              </span>
            )}
            {activeTab === 'events' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 dark:bg-blue-400" style={{ bottom: '-1px' }} />
            )}
          </button>
          
          <button
            onClick={() => {
              setActiveTab('timeline');
              // If timeline needs refresh, do it when switching to the tab
              if (timelineNeedsRefresh) {
                setTimelineKey(prev => prev + 1);
                setTimelineNeedsRefresh(false);
              }
            }}
            className={`flex items-center gap-2 px-4 text-sm font-medium transition-colors relative ${
              activeTab === 'timeline'
                ? 'text-blue-600 dark:text-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            <ClockIcon className="w-4 h-4" />
            Timeline
            {timelineEntryCount > 0 && (
              <span className={`inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold leading-none rounded-full transition-all duration-300 ${
                timelineCountChanged 
                  ? 'text-white bg-green-500 dark:bg-green-600 scale-110 animate-pulse' 
                  : 'text-gray-700 dark:text-gray-200 bg-gray-200 dark:bg-gray-700'
              }`}>
                {timelineEntryCount.toLocaleString()}
              </span>
            )}
            {activeTab === 'timeline' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 dark:bg-blue-400" style={{ bottom: '-1px' }} />
            )}
          </button>
          
          <button
            onClick={() => setActiveTab('report')}
            className={`flex items-center gap-2 px-4 text-sm font-medium transition-colors relative ${
              activeTab === 'report'
                ? 'text-blue-600 dark:text-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            <DocumentChartBarIcon className="w-4 h-4" />
            Report
            {activeTab === 'report' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 dark:bg-blue-400" style={{ bottom: '-1px' }} />
            )}
          </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-hidden bg-white dark:bg-gray-900">
          {/* ChatBox key is stable for this investigation but changes when navigating to different investigation */}
          <div className={`h-full ${activeTab === 'chat' ? '' : 'hidden'}`}>
            <SimplifiedChatBox 
              key={chatKey}
              investigationId={investigationId} 
              onGraphUpdated={() => {
                // Increment key to force TimelineViewer to refresh
                setTimelineKey(prev => prev + 1);
              }}
              onReplicateQuery={handleReplicateQuery}
            />
          </div>
          
          <div className={`h-full ${activeTab === 'events' ? '' : 'hidden'}`}>
            <EventsViewer 
              investigationId={investigationId}
              replicatedQuery={replicatedQuery}
              onQueryApplied={() => setReplicatedQuery(null)}
            />
          </div>
          
          <div className={`h-full bg-white dark:bg-gray-900 ${activeTab === 'timeline' ? '' : 'hidden'}`}>
            <TimelineViewer 
              key={timelineKey} 
              investigationId={investigationId}
            />
          </div>
          
          <div className={`h-full ${activeTab === 'report' ? '' : 'hidden'}`}>
            <ReportGenerator investigationId={investigationId} />
          </div>
        </div>
      </div>

      {/* Jobs Modal */}
      {showJobs && (
        <JobsModal
          investigationId={investigationId}
          onClose={() => setShowJobs(false)}
        />
      )}
    </div>
  );
};

const InvestigationDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  if (!id) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-gray-600 dark:text-gray-400">Invalid investigation</p>
        </div>
      </div>
    );
  }

  return (
    <WebSocketProvider investigationId={id}>
      <InvestigationDetailContent investigationId={id} />
    </WebSocketProvider>
  );
};

export default InvestigationDetail;
