import { useState, useEffect } from 'react';
import type { Status } from '../types';
import { wsManager } from '../api/websocket';

export function useStatus(): Status | null {
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    wsManager.connect();
    const unsubscribe = wsManager.subscribe(setStatus);
    return () => {
      unsubscribe();
    };
  }, []);

  return status;
}
