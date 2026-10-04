'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Heart, X, RotateCcw } from 'lucide-react';
import { MediaItem } from '@/lib/types';
import { MediaSlide, MediaSlideHandle } from './MediaSlide';
import { OverlayControls } from './OverlayControls';

interface HeartEffect {
  id: number;
  x: number;
  y: number;
}

interface SwipeContainerProps {
  items: MediaItem[];
  onAction: (action: 'like' | 'skip', item: MediaItem) => void;
  onUndo?: () => void;
  canUndo?: boolean;
}

export function SwipeContainer({ items, onAction, onUndo, canUndo }: SwipeContainerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isMuted, setIsMuted] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);

  // Drag physics state
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const touchStartX = useRef<number | null>(null);
  const touchStartY = useRef<number | null>(null);
  const touchStartTime = useRef<number>(0);

  // Animations & Feedback
  const [hearts, setHearts] = useState<HeartEffect[]>([]);
  const [seekRipple, setSeekRipple] = useState<'left' | 'right' | null>(null);
  const seekRippleTimeout = useRef<NodeJS.Timeout | null>(null);

  // Tap handling refs
  const lastTapRef = useRef<{ time: number; x: number; y: number } | null>(null);
  const singleTapTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const slideRef = useRef<MediaSlideHandle>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('isMuted');
      if (saved !== null) {
        setIsMuted(saved === 'true');
      }
    } catch {
      // ignore storage access errors
    }
  }, []);

  const handleToggleMute = () => {
    setIsMuted(prev => {
      const next = !prev;
      try {
        localStorage.setItem('isMuted', String(next));
      } catch {
        // ignore storage access errors
      }
      return next;
    });
  };

  const safeIndex = Math.min(currentIndex, Math.max(0, items.length - 1));
  const currentItem = items[safeIndex];

  const handleNext = () => {
    if (currentIndex < items.length - 1) {
      setCurrentIndex(prev => prev + 1);
      setIsPlaying(true);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
      setIsPlaying(true);
    }
  };

  const triggerHeartBurst = (x: number, y: number) => {
    const newHeart = { id: Date.now() + Math.random(), x, y };
    setHearts(prev => [...prev, newHeart]);
    setTimeout(() => {
      setHearts(prev => prev.filter(h => h.id !== newHeart.id));
    }, 750);
  };

  const triggerSeekRipple = (direction: 'left' | 'right') => {
    setSeekRipple(direction);
    if (seekRippleTimeout.current) clearTimeout(seekRippleTimeout.current);
    seekRippleTimeout.current = setTimeout(() => {
      setSeekRipple(null);
    }, 600);
  };

  const handleLike = (burstCoords?: { x: number; y: number }) => {
    if (!currentItem) return;
    const x = burstCoords?.x ?? (typeof window !== 'undefined' ? window.innerWidth / 2 : 200);
    const y = burstCoords?.y ?? (typeof window !== 'undefined' ? window.innerHeight / 2 : 300);
    triggerHeartBurst(x, y);
    onAction('like', currentItem);
  };

  const handleSkip = () => {
    if (!currentItem) return;
    onAction('skip', currentItem);
  };

  // Tap router (Double-tap vs Single-tap)
  const handleTap = (clientX: number, clientY: number) => {
    const now = Date.now();
    const last = lastTapRef.current;

    if (last && now - last.time < 300 && Math.hypot(clientX - last.x, clientY - last.y) < 50) {
      // Double Tap detected!
      if (singleTapTimeoutRef.current) {
        clearTimeout(singleTapTimeoutRef.current);
        singleTapTimeoutRef.current = null;
      }
      lastTapRef.current = null;

      const width = typeof window !== 'undefined' ? window.innerWidth : 400;
      if (clientX < width * 0.3) {
        slideRef.current?.seek(-5);
        triggerSeekRipple('left');
      } else if (clientX > width * 0.7) {
        slideRef.current?.seek(5);
        triggerSeekRipple('right');
      } else {
        handleLike({ x: clientX, y: clientY });
      }
    } else {
      // First tap, queue single-tap play/pause toggle
      lastTapRef.current = { time: now, x: clientX, y: clientY };
      singleTapTimeoutRef.current = setTimeout(() => {
        setIsPlaying(p => !p);
        singleTapTimeoutRef.current = null;
      }, 280);
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' && !e.shiftKey) {
        handleLike();
      } else if (e.key === 'ArrowLeft' && !e.shiftKey) {
        handleSkip();
      } else if (e.key === 'ArrowDown') {
        handleNext();
      } else if (e.key === 'ArrowUp') {
        handlePrev();
      } else if (e.key === ' ') {
        e.preventDefault();
        setIsPlaying(p => !p);
      } else if (e.key.toLowerCase() === 'm') {
        handleToggleMute();
      } else if (e.key.toLowerCase() === 'z' || e.key.toLowerCase() === 'u') {
        if (onUndo) onUndo();
      } else if (e.key.toLowerCase() === 'j' || e.key === '[' || (e.key === 'ArrowLeft' && e.shiftKey)) {
        slideRef.current?.seek(-5);
        triggerSeekRipple('left');
      } else if (e.key.toLowerCase() === 'l' || e.key === ']' || (e.key === 'ArrowRight' && e.shiftKey)) {
        slideRef.current?.seek(5);
        triggerSeekRipple('right');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [currentIndex, currentItem, items.length, onUndo]);

  // Touch handlers with real-time drag feedback
  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
    touchStartTime.current = Date.now();
    setIsDragging(true);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (touchStartX.current === null || touchStartY.current === null) return;
    const dx = e.touches[0].clientX - touchStartX.current;
    const dy = e.touches[0].clientY - touchStartY.current;
    setDragOffset({ x: dx, y: dy });
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    setIsDragging(false);
    const dx = dragOffset.x;
    const dy = dragOffset.y;
    const elapsed = Date.now() - touchStartTime.current;

    setDragOffset({ x: 0, y: 0 });
    touchStartX.current = null;
    touchStartY.current = null;

    if (Math.abs(dx) > 85) {
      if (dx > 85) handleLike();
      else handleSkip();
    } else if (Math.abs(dy) > 85) {
      if (dy < -85) handleNext();
      else handlePrev();
    } else if (Math.abs(dx) < 15 && Math.abs(dy) < 15 && elapsed < 350) {
      const touch = e.changedTouches[0];
      handleTap(touch.clientX, touch.clientY);
    }
  };

  if (!currentItem) {
    return (
      <div className="w-full h-[100dvh] flex flex-col items-center justify-center bg-black text-white p-6 text-center">
        <h2 className="text-2xl font-bold mb-2">🎉 Queue All Cleared!</h2>
        <p className="text-white/60 mb-6">No pending clips remaining. Run /scrape on Telegram or check back later.</p>
        {canUndo && onUndo && (
          <button
            onClick={onUndo}
            className="flex items-center gap-2 px-5 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-full border border-white/20 transition-all font-semibold text-sm active:scale-95"
          >
            <RotateCcw className="w-4 h-4" />
            Undo Last Action
          </button>
        )}
      </div>
    );
  }

  // Dynamic swipe opacity calculations
  const loveOpacity = Math.min(1, Math.max(0, (dragOffset.x - 20) / 100));
  const skipOpacity = Math.min(1, Math.max(0, (-dragOffset.x - 20) / 100));

  return (
    <div
      className="relative w-full h-[100dvh] overflow-hidden bg-black select-none"
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onClick={e => {
        // Desktop click routing
        handleTap(e.clientX, e.clientY);
      }}
    >
      {/* Sliding / Tilting Card Container */}
      <div
        className="w-full h-full relative"
        style={{
          transform: `translate3d(${dragOffset.x}px, ${dragOffset.y * 0.25}px, 0) rotate(${dragOffset.x * 0.04}deg)`,
          transition: isDragging ? 'none' : 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)',
        }}
      >
        <MediaSlide
          ref={slideRef}
          key={currentItem.tweet_url}
          item={currentItem}
          isActive={true}
          isMuted={isMuted}
          isPlaying={isPlaying}
          onTogglePlay={() => setIsPlaying(p => !p)}
          onAutoplayMutedFallback={() => setIsMuted(true)}
        />

        {/* Real-time Swipe Stamp Overlays */}
        {loveOpacity > 0 && (
          <div
            className="absolute top-16 right-8 z-40 border-4 border-emerald-500 text-emerald-400 font-black text-2xl md:text-3xl px-4 py-1.5 rounded-xl uppercase tracking-wider rotate-12 bg-black/40 backdrop-blur-sm pointer-events-none transition-opacity"
            style={{ opacity: loveOpacity }}
          >
            LOVE
          </div>
        )}

        {skipOpacity > 0 && (
          <div
            className="absolute top-16 left-8 z-40 border-4 border-red-500 text-red-400 font-black text-2xl md:text-3xl px-4 py-1.5 rounded-xl uppercase tracking-wider -rotate-12 bg-black/40 backdrop-blur-sm pointer-events-none transition-opacity"
            style={{ opacity: skipOpacity }}
          >
            SKIP
          </div>
        )}
      </div>

      {/* Heart Burst Particles */}
      {hearts.map(h => (
        <div
          key={h.id}
          className="fixed pointer-events-none z-50 animate-heart-burst"
          style={{ left: `${h.x}px`, top: `${h.y}px` }}
        >
          <Heart className="w-24 h-24 text-rose-500 fill-rose-500 drop-shadow-[0_0_25px_rgba(244,63,94,0.9)]" />
        </div>
      ))}

      {/* Seek Ripple Feedback */}
      {seekRipple === 'left' && (
        <div className="fixed top-1/2 left-8 -translate-y-1/2 z-50 pointer-events-none animate-ripple bg-black/70 backdrop-blur-md border border-white/20 text-white font-bold text-sm px-4 py-2 rounded-full flex items-center gap-1.5 shadow-2xl">
          <span>⏪</span>
          <span>-5s</span>
        </div>
      )}
      {seekRipple === 'right' && (
        <div className="fixed top-1/2 right-8 -translate-y-1/2 z-50 pointer-events-none animate-ripple bg-black/70 backdrop-blur-md border border-white/20 text-white font-bold text-sm px-4 py-2 rounded-full flex items-center gap-1.5 shadow-2xl">
          <span>+5s</span>
          <span>⏩</span>
        </div>
      )}

      {/* Overlay UI Controls */}
      <OverlayControls
        item={currentItem}
        queueCount={items.length}
        isMuted={isMuted}
        onToggleMute={handleToggleMute}
        onLike={() => handleLike()}
        onSkip={handleSkip}
      />

      {/* Desktop Hotkey Legend Pill */}
      <div className="hidden md:flex items-center gap-2 text-xs text-white/50 bg-black/50 backdrop-blur-md px-3.5 py-1.5 rounded-full border border-white/10 pointer-events-none fixed bottom-4 left-4 z-40">
        <span>← Skip</span>
        <span>•</span>
        <span>Love →</span>
        <span>•</span>
        <span>Space Pause</span>
        <span>•</span>
        <span>M Mute</span>
        <span>•</span>
        <span>J/L Seek</span>
        <span>•</span>
        <span>Z Undo</span>
      </div>
    </div>
  );
}
