'use client';

import React, { useRef, useEffect } from 'react';
import { MediaItem } from '@/lib/types';

interface MediaSlideProps {
  item: MediaItem;
  isActive: boolean;
  isMuted: boolean;
  isPlaying: boolean;
}

export function MediaSlide({ item, isActive, isMuted, isPlaying }: MediaSlideProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!videoRef.current || item.type !== 'video') return;
    if (isActive && isPlaying) {
      videoRef.current.play().catch(() => {});
    } else {
      videoRef.current.pause();
    }
  }, [isActive, isPlaying, item.type]);

  // Duration & Resolution format
  const durationSec = item.duration_millis ? Math.round(item.duration_millis / 1000) : null;
  const durationStr = durationSec ? `${Math.floor(durationSec / 60)}:${(durationSec % 60).toString().padStart(2, '0')}` : null;
  const resolutionStr = item.width && item.height ? `${Math.min(item.width, item.height)}p` : null;

  return (
    <div className="relative w-full h-[100dvh] flex items-center justify-center bg-black overflow-hidden select-none">
      {item.type === 'video' ? (
        <video
          ref={videoRef}
          src={item.url}
          className="w-full h-full object-contain"
          playsInline
          loop
          muted={isMuted}
          preload="auto"
        />
      ) : (
        <img
          src={item.url}
          alt={item.text || 'Media'}
          className="w-full h-full object-contain"
        />
      )}

      {/* Top Floating Badge */}
      {(durationStr || resolutionStr) && (
        <div className="absolute top-4 left-4 z-20 px-3 py-1 bg-black/60 backdrop-blur-md rounded-full text-xs font-semibold text-white/90 border border-white/10 flex items-center gap-1.5 shadow-lg">
          {durationStr && <span>⏱️ {durationStr}</span>}
          {durationStr && resolutionStr && <span>•</span>}
          {resolutionStr && <span>{resolutionStr}</span>}
        </div>
      )}
    </div>
  );
}
