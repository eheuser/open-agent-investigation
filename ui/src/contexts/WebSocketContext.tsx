import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';

interface WebSocketMessage {
  type: string;
  [key: string]: any;
}

type MessageListener = (message: WebSocketMessage) => void;

interface WebSocketContextType {
  isConnected: boolean;
  sendMessage: (message: WebSocketMessage) => void;
  subscribe: (listener: MessageListener) => () => void;
  ws: WebSocket | null;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

interface WebSocketProviderProps {
  investigationId: string;
  children: React.ReactNode;
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ investigationId, children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef<Set<MessageListener>>(new Set());
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const messageQueueRef = useRef<WebSocketMessage[]>([]);
  const MAX_RECONNECT_ATTEMPTS = 10;
  const RECONNECT_DELAY = 2000;

  const subscribe = useCallback((listener: MessageListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const broadcastMessage = useCallback((message: WebSocketMessage) => {
    listenersRef.current.forEach(listener => {
      try {
        listener(message);
      } catch (error) {
        console.error('Error in WebSocket listener:', error);
      }
    });
  }, []);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      messageQueueRef.current.push(message);
      return;
    }

    try {
      wsRef.current.send(JSON.stringify(message));
    } catch (error) {
      console.error(`[WebSocket] Failed to send message:`, error);
      messageQueueRef.current.push(message);
    }
  }, []);

  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    // Close existing connection if any
    if (wsRef.current) {
      wsRef.current.close(1000, 'Reconnecting');
      wsRef.current = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
    const wsUrl = `${protocol}//${host}:${port}/api/v1/chat/ws/${investigationId}?token=${token}`;
    
    //console.log(`[WebSocket] Connecting to investigation ${investigationId}`);
    const websocket = new WebSocket(wsUrl);
    wsRef.current = websocket;

    websocket.onopen = () => {
      //console.log(`[WebSocket] Connected to investigation ${investigationId}`);
      setIsConnected(true);
      setWs(websocket);
      reconnectAttemptsRef.current = 0;
      
      // Send queued messages
      while (messageQueueRef.current.length > 0) {
        const queuedMessage = messageQueueRef.current.shift();
        if (queuedMessage) {
          try {
            websocket.send(JSON.stringify(queuedMessage));
          } catch (error) {
            console.error('Failed to send queued message:', error);
          }
        }
      }
    };

    websocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        broadcastMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    websocket.onerror = () => {};

    websocket.onclose = (event) => {
      //console.log(`[WebSocket] Disconnected from investigation ${investigationId}, code: ${event.code}`);
      setIsConnected(false);
      setWs(null);
      wsRef.current = null;

      // Don't reconnect on normal closure or if investigation changed
      if (event.code !== 1000 && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttemptsRef.current++;
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null;
          connect();
        }, RECONNECT_DELAY);
      }
    };
  }, [investigationId, broadcastMessage]);

  useEffect(() => {
    // Clear any pending reconnect attempts
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Reset reconnect counter for new investigation
    reconnectAttemptsRef.current = 0;

    // Clear message queue when investigation changes
    messageQueueRef.current = [];

    // Connect to the current investigation
    connect();

    return () => {
      // Clear reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      // Close WebSocket connection
      if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
          wsRef.current.close(1000, 'Investigation changed');
        }
        wsRef.current = null;
      }

      setIsConnected(false);
      setWs(null);
    };
  }, [investigationId, connect]);

  const value: WebSocketContextType = {
    isConnected,
    sendMessage,
    subscribe,
    ws,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocketContext = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
};
