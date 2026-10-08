'use client';

import React, { useEffect, useState, useRef } from 'react';
import { RotateCcw } from 'lucide-react';
import { MediaItem } from '@/lib/types';
import { SwipeContainer } from '@/components/SwipeContainer';

interface UndoState {
  item: MediaItem;
  action: 'like' | 'skip';
}

export default function HomePage() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeList, setActiveList] = useState<string>('1');

  // Undo Toast state
  const [undoState, setUndoState] = useState<UndoState | null>(null);
  const undoTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/queue');
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
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  const handleAction = async (action: 'like' | 'skip', item: MediaItem) => {
    // Optimistic removal from UI
    setItems(prev => prev.filter(i => i.tweet_url !== item.tweet_url));

    // Clear any previous undo timer
    if (undoTimeoutRef.current) {
      clearTimeout(undoTimeoutRef.current);
    }

    // Set new undo state with 4.5s lifespan
    setUndoState({ item, action });
    undoTimeoutRef.current = setTimeout(() => {
      setUndoState(null);
    }, 4500);

    try {
      await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, tweetUrl: item.tweet_url }),
      });
    } catch (e) {
      console.error(`Failed to execute ${action}:`, e);
    }
  };

  const handleUndo = async () => {
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
      });
    } catch (e) {
      console.error('Failed to undo action:', e);
    }
  };

  const handleSwitchList = async (targetList: '1' | '2') => {
    setActiveList(targetList);
    try {
      await fetch('/api/list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_list: targetList }),
      });
    } catch (e) {
      console.error('Failed to switch active list:', e);
    }
  };

  if (loading) {
    return (
      <div className="w-full h-[100dvh] flex items-center justify-center bg-black text-white">
        <div className="w-8 h-8 border-4 border-white/20 border-t-white rounded-full animate-spin" />
      </div>
    );
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
