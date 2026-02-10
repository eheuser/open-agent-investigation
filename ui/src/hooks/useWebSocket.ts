import { useEffect, useRef } from 'react';

export const useWebSocket = (investigationId: string) => {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${location.host}/api/v1/ws/${investigationId}`);
    wsRef.current = ws;

    ws.onopen = () => { };
    ws.onclose = () => { };

    return () => {
      ws.close();
    };
  }, [investigationId]);

  return wsRef.current;
};
