'use client';

import React, { useEffect, useState } from 'react';
import { MediaItem } from '@/lib/types';
import { SwipeContainer } from '@/components/SwipeContainer';

export default function HomePage() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchQueue = async () => {
    try {
      const res = await fetch('/api/queue');
      const data = await res.json();
      if (data.queue) setItems(data.queue);
    } catch (e) {
      console.error('Failed to load queue:', e);
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

  return <SwipeContainer items={items} onAction={handleAction} />;
}
