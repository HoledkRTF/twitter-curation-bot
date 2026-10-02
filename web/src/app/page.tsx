'use client';

import React, { useEffect, useState } from 'react';
import { MediaItem } from '@/lib/types';
import { SwipeContainer } from '@/components/SwipeContainer';

export default function HomePage() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return <SwipeContainer items={items} onAction={handleAction} />;
}
