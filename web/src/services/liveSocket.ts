import { useEffect, useRef } from 'react';
import { useLiveStore } from '../stores/liveStore';

const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
const defaultHq = isLocal ? '192.168.137.1' : (typeof window !== 'undefined' && window.location.hostname ? window.location.hostname : '192.168.137.1');
const WS_BASE_URL = import.meta.env.VITE_HQ_WS_URL || (
  typeof window !== 'undefined' && window.location.protocol === 'https:'
    ? `wss://${defaultHq}:8000/ws/live`
    : `ws://${defaultHq}:8000/ws/live`
);

export function useLiveSocket() {
  const apply = useLiveStore((s) => s.apply);
  const setConnected = useLiveStore((s) => s.setConnected);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let retryTimeout: any = null;
    let retryDelay = 1000;
    let isMounted = true;

    const connect = () => {
      try {
        const ws = new WebSocket(WS_BASE_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMounted) return;
          setConnected(true);
          retryDelay = 1000;
          // Request initial counters
          ws.send(JSON.stringify({ action: 'get_counters', tenant_id: 'acme' }));
        };

        ws.onmessage = (event) => {
          if (!isMounted) return;
          try {
            if (event.data === 'pong') return;
            const parsed = JSON.parse(event.data);
            apply(parsed);
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };

        ws.onerror = () => {
          // Handled by onclose
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setConnected(false);
          retryTimeout = setTimeout(() => {
            retryDelay = Math.min(retryDelay * 1.5, 10000);
            connect();
          }, retryDelay);
        };
      } catch (err) {
        setConnected(false);
        retryTimeout = setTimeout(connect, 3000);
      }
    };

    connect();

    // Periodic ping to keep alive
    const pingInterval = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping');
      }
    }, 15000);

    return () => {
      isMounted = false;
      clearInterval(pingInterval);
      if (retryTimeout) clearTimeout(retryTimeout);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [apply, setConnected]);
}
