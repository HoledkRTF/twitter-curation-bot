'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { RotateCcw } from 'lucide-react';
import { MediaItem } from '@/lib/types';
import { SwipeContainer } from '@/components/SwipeContainer';

interface UndoState {
  item: MediaItem;
  action: 'like' | 'skip';
}

function SkeletonLoader() {
  return (
    <div className="w-full h-[100dvh] bg-black text-white relative overflow-hidden flex flex-col justify-between p-4 md:p-6 select-none">
      {/* Background Pulse Gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-neutral-900/60 via-black/40 to-neutral-950 animate-pulse pointer-events-none" />

      {/* Top Bar Skeleton */}
      <div className="relative z-10 flex justify-between items-center w-full">
        <div className="flex items-center gap-2 bg-neutral-900/80 rounded-full p-1 border border-white/10">
          <div className="w-16 h-6 rounded-full bg-white/20 animate-pulse" />
          <div className="w-16 h-6 rounded-full bg-white/10 animate-pulse" />
        </div>
        <div className="w-20 h-7 rounded-full bg-neutral-900/80 border border-white/10 animate-pulse" />
      </div>

      {/* Center Media Placeholder */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center animate-pulse">
          <div className="w-0 h-0 border-y-8 border-y-transparent border-l-12 border-l-white/20 ml-1" />
        </div>
      </div>

      {/* Floating Action Buttons Skeleton (Right Edge) */}
      <div className="absolute right-4 bottom-24 z-10 flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-full bg-neutral-900/80 border border-white/10 animate-pulse" />
        <div className="w-12 h-12 rounded-full bg-neutral-900/80 border border-white/10 animate-pulse" />
        <div className="w-12 h-12 rounded-full bg-neutral-900/80 border border-white/10 animate-pulse" />
      </div>

      {/* Bottom Metadata Skeleton */}
      <div className="relative z-10 flex flex-col gap-2 max-w-[80%] pb-6">
        <div className="w-28 h-5 rounded-md bg-sky-400/20 animate-pulse" />
        <div className="w-64 h-4 rounded-md bg-white/15 animate-pulse" />
        <div className="w-44 h-4 rounded-md bg-white/10 animate-pulse" />
        <div className="flex gap-2 mt-2">
          <div className="w-16 h-5 rounded bg-white/10 animate-pulse" />
          <div className="w-14 h-5 rounded bg-white/10 animate-pulse" />
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeList, setActiveList] = useState<string>('1');

  // In-flight guard to prevent duplicate API calls (03 / 31)
  const isFetchingRef = useRef(false);

  // Undo Toast state
  const [undoState, setUndoState] = useState<UndoState | null>(null);
  const undoTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchQueue = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/queue?limit=50', {
        signal: AbortSignal.timeout(10000), // 12 / 31: Timeout for external calls
      });
      if (!res.ok) {
        throw new Error(`Failed to load queue (${res.status})`);
      }
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      if (data.queue) setItems(data.queue);
      if (data.active_list) setActiveList(String(data.active_list));
    } catch (e: any) {
      console.error('Failed to load queue:', e);
      setError(e?.message || 'Failed to load queue');
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleAction = useCallback(async (action: 'like' | 'skip', item: MediaItem) => {
    // 14 / 31: Optimistic removal from UI before server responds
    setItems(prev => prev.filter(i => i.tweet_url !== item.tweet_url));

    if (undoTimeoutRef.current) {
      clearTimeout(undoTimeoutRef.current);
    }

    setUndoState({ item, action });
    undoTimeoutRef.current = setTimeout(() => {
      setUndoState(null);
    }, 4500);

    try {
      await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, tweetUrl: item.tweet_url }),
        signal: AbortSignal.timeout(8000),
      });
    } catch (e) {
      console.error(`Failed to execute ${action}:`, e);
    }
  }, []);

  const handleUndo = useCallback(async () => {
    if (!undoState) return;

    const { item, action } = undoState;

    if (undoTimeoutRef.current) {
      clearTimeout(undoTimeoutRef.current);
      undoTimeoutRef.current = null;
    }
    setUndoState(null);

    // Optimistically restore item to top of queue
    setItems(prev => [item, ...prev]);

    try {
      await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'undo',
          item,
          previousAction: action,
        }),
        signal: AbortSignal.timeout(8000),
      });
    } catch (e) {
      console.error('Failed to undo action:', e);
    }
  }, [undoState]);

  const handleSwitchList = useCallback(async (targetList: '1' | '2') => {
    setActiveList(targetList);
    try {
      await fetch('/api/list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_list: targetList }),
        signal: AbortSignal.timeout(8000),
      });
      // Refresh queue for switched list
      await fetchQueue();
    } catch (e) {
      console.error('Failed to switch active list:', e);
    }
  }, [fetchQueue]);

  if (loading) {
    return <SkeletonLoader />;
  }

  if (error) {
    return (
      <div className="w-full h-[100dvh] flex flex-col items-center justify-center bg-black text-white p-6 text-center">
        <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6 max-w-md flex flex-col items-center gap-4">
          <p className="text-red-400 font-semibold">{error}</p>
          <button
            onClick={() => fetchQueue()}
            className="px-5 py-2.5 bg-white text-black font-semibold rounded-full hover:bg-white/90 active:scale-95 transition-all text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <main className="relative w-full h-[100dvh] bg-black overflow-hidden">
      <SwipeContainer
        items={items}
        onAction={handleAction}
        onUndo={handleUndo}
        canUndo={!!undoState}
        activeList={activeList}
        onSwitchList={handleSwitchList}
      />

      {/* Floating Undo Toast */}
      {undoState && (
        <div className="fixed bottom-28 md:bottom-24 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-2 bg-neutral-900/90 text-white rounded-full border border-white/20 shadow-2xl backdrop-blur-md pointer-events-auto transition-all animate-bounce">
          <span className="text-xs md:text-sm font-medium text-white/80">
            {undoState.action === 'like' ? 'Loved clip' : 'Skipped clip'}
          </span>
          <button
            onClick={handleUndo}
            className="px-3 py-1 bg-white text-black text-xs font-bold rounded-full hover:bg-white/90 active:scale-95 transition-all flex items-center gap-1 shadow"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Undo
          </button>
        </div>
      )}
    </main>
  );
}
