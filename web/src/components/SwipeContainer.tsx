'use client';

import React, { useState, useEffect, useRef } from 'react';
import { MediaItem } from '@/lib/types';
import { MediaSlide } from './MediaSlide';
import { OverlayControls } from './OverlayControls';

interface SwipeContainerProps {
  items: MediaItem[];
  onAction: (action: 'like' | 'skip', item: MediaItem) => void;
}

export function SwipeContainer({ items, onAction }: SwipeContainerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isMuted, setIsMuted] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);

  const touchStartX = useRef<number | null>(null);
  const touchStartY = useRef<number | null>(null);

  const currentItem = items[currentIndex];

  const handleNext = () => {
    if (currentIndex < items.length - 1) {
      setCurrentIndex(prev => prev + 1);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
    }
  };

  const handleLike = () => {
    if (!currentItem) return;
    onAction('like', currentItem);
  };

  const handleSkip = () => {
    if (!currentItem) return;
    onAction('skip', currentItem);
  };

  // Keyboard navigation
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') handleLike();
      else if (e.key === 'ArrowLeft') handleSkip();
      else if (e.key === 'ArrowDown') handleNext();
      else if (e.key === 'ArrowUp') handlePrev();
      else if (e.key === ' ') {
        e.preventDefault();
        setIsPlaying(p => !p);
      } else if (e.key.toLowerCase() === 'm') {
        setIsMuted(m => !m);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [currentIndex, currentItem, items.length]);

  // Touch Swipe
  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null || touchStartY.current === null) return;
    const diffX = e.changedTouches[0].clientX - touchStartX.current;
    const diffY = e.changedTouches[0].clientY - touchStartY.current;

    const threshold = 60;
    if (Math.abs(diffX) > Math.abs(diffY)) {
      if (diffX > threshold) handleLike(); // Swipe right = Love
      else if (diffX < -threshold) handleSkip(); // Swipe left = Skip
    } else {
      if (diffY < -threshold) handleNext(); // Swipe up = Next
      else if (diffY > threshold) handlePrev(); // Swipe down = Prev
    }

    touchStartX.current = null;
    touchStartY.current = null;
  };

  if (!currentItem) {
    return (
      <div className="w-full h-[100dvh] flex flex-col items-center justify-center bg-black text-white p-6 text-center">
        <h2 className="text-2xl font-bold mb-2">🎉 Queue All Cleared!</h2>
        <p className="text-white/60">No pending clips remaining. Run /scrape on Telegram or check back later.</p>
      </div>
    );
  }

  return (
    <div
      className="relative w-full h-[100dvh] overflow-hidden"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      onClick={() => setIsPlaying(p => !p)}
    >
      <MediaSlide
        item={currentItem}
        isActive={true}
        isMuted={isMuted}
        isPlaying={isPlaying}
      />

      <OverlayControls
        item={currentItem}
        queueCount={items.length}
        isMuted={isMuted}
        onToggleMute={() => setIsMuted(!isMuted)}
        onLike={handleLike}
        onSkip={handleSkip}
      />
    </div>
  );
}
