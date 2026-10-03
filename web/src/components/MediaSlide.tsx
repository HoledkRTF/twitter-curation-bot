'use client';

import React, { useRef, useEffect, useState } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { MediaItem } from '@/lib/types';

interface MediaSlideProps {
  item: MediaItem;
  isActive: boolean;
  isMuted: boolean;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onAutoplayMutedFallback?: () => void;
}

export function MediaSlide({
  item,
  isActive,
  isMuted,
  isPlaying,
  onTogglePlay,
  onAutoplayMutedFallback,
}: MediaSlideProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [srcIndex, setSrcIndex] = useState(0);
  const [useProxy, setUseProxy] = useState(false);
  const [imageUseProxy, setImageUseProxy] = useState(false);

  // Reset indices and proxy fallback when active item changes
  useEffect(() => {
    setSrcIndex(0);
    setUseProxy(false);
    setImageUseProxy(false);
    setIsLoading(true);
  }, [item.tweet_url, item.url]);

  const allUrls = item.urls && item.urls.length > 0 ? item.urls : [item.url];
  const rawVideoSrc = allUrls[srcIndex] || item.url;
  const currentVideoSrc = useProxy
    ? `/api/proxy?url=${encodeURIComponent(rawVideoSrc)}`
    : rawVideoSrc;

  const currentImageSrc = imageUseProxy
    ? `/api/proxy?url=${encodeURIComponent(item.url)}`
    : item.url;

  // Imperatively sync muted property to satisfy browser Autoplay policies
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted;
      videoRef.current.defaultMuted = isMuted;
      videoRef.current.setAttribute('referrerpolicy', 'no-referrer');
    }
  }, [isMuted]);

  // Handle Play/Pause with Autoplay fallback
  useEffect(() => {
    const video = videoRef.current;
    if (!video || item.type !== 'video' || !isActive) return;

    if (isPlaying) {
      const playPromise = video.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            setIsLoading(false);
          })
          .catch((err: any) => {
            if (err.name === 'NotAllowedError') {
              // Browser blocked unmuted autoplay - fallback to muted so it plays!
              video.muted = true;
              video.play().catch(() => {});
              if (onAutoplayMutedFallback) {
                onAutoplayMutedFallback();
              }
            }
          });
      }
    } else {
      video.pause();
    }
  }, [isActive, isPlaying, currentVideoSrc, item.type, onAutoplayMutedFallback]);

  // Handle video error: first try proxy fallback, then try next URL variant
  const handleVideoError = () => {
    if (!useProxy) {
      setIsLoading(true);
      setUseProxy(true);
    } else if (srcIndex + 1 < allUrls.length) {
      setIsLoading(true);
      setSrcIndex(prev => prev + 1);
      setUseProxy(false);
    } else {
      setIsLoading(false);
    }
  };

  const handleImageError = () => {
    if (!imageUseProxy) {
      setIsLoading(true);
      setImageUseProxy(true);
    } else {
      setIsLoading(false);
    }
  };

  // Duration & Resolution format
  const durationSec = item.duration_millis ? Math.round(item.duration_millis / 1000) : null;
  const durationStr = durationSec
    ? `${Math.floor(durationSec / 60)}:${(durationSec % 60).toString().padStart(2, '0')}`
    : null;
  const resolutionStr = item.width && item.height ? `${Math.min(item.width, item.height)}p` : null;

  return (
    <div
      onClick={onTogglePlay}
      className="relative w-full h-[100dvh] flex items-center justify-center bg-black overflow-hidden select-none cursor-pointer"
    >
      {item.type === 'video' ? (
        <video
          ref={videoRef}
          src={currentVideoSrc}
          className="w-full h-full object-contain"
          playsInline
          loop
          muted={isMuted}
          preload="auto"
          {...({ referrerPolicy: 'no-referrer' } as any)}
          onWaiting={() => setIsLoading(true)}
          onPlaying={() => setIsLoading(false)}
          onCanPlay={() => setIsLoading(false)}
          onError={handleVideoError}
        />
      ) : (
        <img
          src={currentImageSrc}
          alt={item.text || 'Media'}
          className="w-full h-full object-contain"
          referrerPolicy="no-referrer"
          onLoad={() => setIsLoading(false)}
          onError={handleImageError}
        />
      )}

      {/* Buffering Spinner */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10 bg-black/20">
          <Loader2 className="w-10 h-10 text-white/80 animate-spin" />
        </div>
      )}

      {/* Centered Play Icon Overlay when Paused */}
      {!isPlaying && !isLoading && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
          <div className="w-16 h-16 rounded-full bg-black/60 backdrop-blur-md flex items-center justify-center text-white/90 shadow-2xl border border-white/20">
            <Play className="w-8 h-8 fill-white translate-x-0.5" />
          </div>
        </div>
      )}

      {/* Top Floating Badge */}
      {(durationStr || resolutionStr) && (
        <div className="absolute top-4 left-4 z-20 px-3 py-1 bg-black/60 backdrop-blur-md rounded-full text-xs font-semibold text-white/90 border border-white/10 flex items-center gap-1.5 shadow-lg pointer-events-none">
          {durationStr && <span>⏱️ {durationStr}</span>}
          {durationStr && resolutionStr && <span>•</span>}
          {resolutionStr && <span>{resolutionStr}</span>}
        </div>
      )}
    </div>
  );
}
