interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

let queueCache: CacheEntry<any> | null = null;
const QUEUE_TTL_MS = 5000; // 5 seconds in-memory TTL

export function getCachedQueue<T>(): T | null {
  if (queueCache && Date.now() - queueCache.timestamp < QUEUE_TTL_MS) {
    return queueCache.data as T;
  }
  return null;
}

export function setCachedQueue(data: any): void {
  queueCache = {
    data,
    timestamp: Date.now(),
  };
}

export function invalidateQueueCache(): void {
  queueCache = null;
}
