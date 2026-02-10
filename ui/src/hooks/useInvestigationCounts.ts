import { useState, useEffect, useCallback } from 'react';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import api from '../services/api';

interface UseInvestigationCountsProps {
  investigationId: string;
  activeTab: string;
  onTimelineRefresh?: () => void;
}

interface UseInvestigationCountsReturn {
  eventCount: number;
  timelineEntryCount: number;
  timelineCountChanged: boolean;
}

export const useInvestigationCounts = ({
  investigationId,
  activeTab,
  onTimelineRefresh,
}: UseInvestigationCountsProps): UseInvestigationCountsReturn => {
  const { subscribe } = useWebSocketContext();
  const [eventCount, setEventCount] = useState<number>(0);
  const [timelineEntryCount, setTimelineEntryCount] = useState<number>(0);
  const [timelineCountChanged, setTimelineCountChanged] = useState(false);

  // Fetch initial counts
  useEffect(() => {
    const fetchEventCount = async () => {
      try {
        const response = await api.get(`/api/v1/events/${investigationId}?limit=1&offset=0`);
        setEventCount(response.data.total || 0);
      } catch (err) {
        console.error('Failed to fetch event count:', err);
      }
    };

    const fetchTimelineCounts = async () => {
      try {
        const response = await api.get(`/api/v1/timeline/${investigationId}?limit=1`);
        setTimelineEntryCount(response.data.total || 0);
      } catch (err) {
        console.error('Failed to fetch timeline counts:', err);
      }
    };

    fetchEventCount();
    fetchTimelineCounts();
  }, [investigationId]);

  // Handle WebSocket messages for count updates
  const handleCountMessage = useCallback((message: any) => {
    // Only handle count-related messages
    if (message.type === 'events_inserted') {
      // Refetch event count
      api.get(`/api/v1/events/${investigationId}?limit=1&offset=0`)
        .then(response => setEventCount(response.data.total || 0))
        .catch(err => console.error('Failed to fetch event count:', err));
    }

    if (message.type === 'timeline_mutated' || message.type === 'timeline_updated') {
      // Refetch both counts
      api.get(`/api/v1/events/${investigationId}?limit=1&offset=0`)
        .then(response => setEventCount(response.data.total || 0))
        .catch(err => console.error('Failed to fetch event count:', err));

      api.get(`/api/v1/timeline/${investigationId}?limit=1`)
        .then(response => setTimelineEntryCount(response.data.total || 0))
        .catch(err => console.error('Failed to fetch timeline counts:', err));
    }

    if (message.type === 'timeline_entry_added') {
      setTimelineEntryCount(prev => prev + 1);
      // Trigger animation
      setTimelineCountChanged(true);
      setTimeout(() => setTimelineCountChanged(false), 1000);

      // Notify parent that timeline needs refresh
      if (onTimelineRefresh) {
        onTimelineRefresh();
      }
    }

    if (message.type === 'timeline_entry_removed') {
      setTimelineEntryCount(prev => Math.max(0, prev - 1));
      // Trigger animation
      setTimelineCountChanged(true);
      setTimeout(() => setTimelineCountChanged(false), 1000);

      // Notify parent that timeline needs refresh
      if (onTimelineRefresh) {
        onTimelineRefresh();
      }
    }

    if (message.type === 'agent_completed') {
      // Refetch timeline counts
      api.get(`/api/v1/timeline/${investigationId}?limit=1`)
        .then(response => setTimelineEntryCount(response.data.total || 0))
        .catch(err => console.error('Failed to fetch timeline counts:', err));

      // Notify parent that timeline needs refresh
      if (onTimelineRefresh) {
        onTimelineRefresh();
      }
    }
  }, [investigationId, activeTab, onTimelineRefresh]);

  // Subscribe to WebSocket messages
  useEffect(() => {
    const unsubscribe = subscribe(handleCountMessage);
    return unsubscribe;
  }, [subscribe, handleCountMessage]);

  return {
    eventCount,
    timelineEntryCount,
    timelineCountChanged,
  };
};
