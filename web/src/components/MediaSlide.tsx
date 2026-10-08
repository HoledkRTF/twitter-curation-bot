'use client';

import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef } from 'react';
import { Play, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { MediaItem } from '@/lib/types';

export interface MediaSlideHandle {
  seek: (delta: number) => void;
  getDuration: () => number;
  getCurrentTime: () => number;
}

interface MediaSlideProps {
  item: MediaItem;
  isActive: boolean;
  isMuted: boolean;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onAutoplayMutedFallback?: () => void;
}

export const MediaSlide = forwardRef<MediaSlideHandle, MediaSlideProps>(function MediaSlide(
  {
    item,
    isActive,
    isMuted,
    isPlaying,
    onTogglePlay,
    onAutoplayMutedFallback,
  },
  ref
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [srcIndex, setSrcIndex] = useState(0);
  const [albumIndex, setAlbumIndex] = useState(0);
  const [useProxy, setUseProxy] = useState(false);
  const [imageUseProxy, setImageUseProxy] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // Expose seeking control to parent
  useImperativeHandle(ref, () => ({
    seek: (delta: number) => {
      if (videoRef.current) {
        const d = videoRef.current.duration || 0;
        const newTime = Math.max(0, Math.min(d, videoRef.current.currentTime + delta));
        videoRef.current.currentTime = newTime;
        setCurrentTime(newTime);
      }
    },
    getDuration: () => duration,
    getCurrentTime: () => currentTime,
  }));

  // Reset indices, proxy fallback, and timing when active item changes
  useEffect(() => {
    setSrcIndex(0);
    setAlbumIndex(0);
    setUseProxy(false);
    setImageUseProxy(false);
    setIsLoading(true);
    setCurrentTime(0);
    setDuration(0);
  }, [item.tweet_url, item.url]);

  const allUrls = item.urls && item.urls.length > 0 ? item.urls : [item.url];
  const rawVideoSrc = allUrls[srcIndex] || item.url;
  const currentVideoSrc = useProxy
    ? `/api/proxy?url=${encodeURIComponent(rawVideoSrc)}`
    : rawVideoSrc;

  const isAlbum = item.type === 'album' || (item.type === 'photo' && !!item.urls && item.urls.length > 1);
  const albumUrls = isAlbum && item.urls && item.urls.length > 0 ? item.urls : [item.url];
  const currentPhotoUrl = albumUrls[albumIndex] || item.url;

  const currentImageSrc = imageUseProxy
    ? `/api/proxy?url=${encodeURIComponent(currentPhotoUrl)}`
    : currentPhotoUrl;

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

  const handlePrevPhoto = (e: React.MouseEvent | React.TouchEvent) => {
    e.stopPropagation();
    if (albumIndex > 0) {
      setAlbumIndex(prev => prev - 1);
      setIsLoading(true);
      setImageUseProxy(false);
    }
  };

  const handleNextPhoto = (e: React.MouseEvent | React.TouchEvent) => {
    e.stopPropagation();
    if (albumIndex < albumUrls.length - 1) {
      setAlbumIndex(prev => prev + 1);
      setIsLoading(true);
      setImageUseProxy(false);
    }
  };

  const handleScrub = (e: React.MouseEvent<HTMLDivElement> | React.TouchEvent<HTMLDivElement>) => {
    e.stopPropagation();
    if (!videoRef.current || !duration) return;
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    videoRef.current.currentTime = pct * duration;
    setCurrentTime(pct * duration);
  };

  // Duration & Resolution format
  const durationSec = duration > 0 ? Math.round(duration) : (item.duration_millis ? Math.round(item.duration_millis / 1000) : null);
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
          className="w-full h-full object-contain pointer-events-none"
          playsInline
          loop
          muted={isMuted}
          preload="auto"
          {...({ referrerPolicy: 'no-referrer' } as any)}
          onTimeUpdate={() => {
            if (videoRef.current) setCurrentTime(videoRef.current.currentTime);
          }}
          onLoadedMetadata={() => {
            if (videoRef.current) setDuration(videoRef.current.duration);
          }}
          onWaiting={() => setIsLoading(true)}
          onPlaying={() => setIsLoading(false)}
          onCanPlay={() => setIsLoading(false)}
          onError={handleVideoError}
        />
      ) : (
        <div className="relative w-full h-full flex items-center justify-center">
          <img
            key={currentPhotoUrl}
            src={currentImageSrc}
            alt={item.text || 'Media'}
            className="w-full h-full object-contain pointer-events-none"
            referrerPolicy="no-referrer"
            onLoad={() => setIsLoading(false)}
            onError={handleImageError}
          />

          {/* Album Indicator & Pagination Dots */}
          {isAlbum && albumUrls.length > 1 && (
            <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 px-3.5 py-1.5 bg-black/60 backdrop-blur-md rounded-full border border-white/10 shadow-lg pointer-events-none">
              <span className="text-xs font-bold text-white/90 mr-1">
                📸 {albumIndex + 1}/{albumUrls.length}
              </span>
              {albumUrls.map((_, idx) => (
                <span
                  key={idx}
                  className={`h-1.5 rounded-full transition-all ${
                    idx === albumIndex ? 'w-4 bg-white shadow' : 'w-1.5 bg-white/40'
                  }`}
                />
              ))}
            </div>
          )}

          {/* Left / Right Carousel Arrow Buttons */}
          {isAlbum && albumUrls.length > 1 && albumIndex > 0 && (
            <button
              onClick={handlePrevPhoto}
              onTouchStart={handlePrevPhoto}
              aria-label="Previous photo"
              className="absolute left-3 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full bg-black/60 backdrop-blur-md border border-white/10 text-white flex items-center justify-center hover:bg-black/90 active:scale-90 transition-all shadow-xl cursor-pointer pointer-events-auto"
            >
              <ChevronLeft className="w-6 h-6" />
            </button>
          )}

          {isAlbum && albumUrls.length > 1 && albumIndex < albumUrls.length - 1 && (
            <button
              onClick={handleNextPhoto}
              onTouchStart={handleNextPhoto}
              aria-label="Next photo"
              className="absolute right-3 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full bg-black/60 backdrop-blur-md border border-white/10 text-white flex items-center justify-center hover:bg-black/90 active:scale-90 transition-all shadow-xl cursor-pointer pointer-events-auto"
            >
              <ChevronRight className="w-6 h-6" />
            </button>
          )}
        </div>
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

      {/* Bottom Video Progress Scrub Bar */}
      {item.type === 'video' && duration > 0 && (
        <div
          onClick={handleScrub}
          onTouchStart={handleScrub}
          className="absolute bottom-0 left-0 right-0 h-4 z-40 group flex items-end cursor-pointer"
        >
          <div className="w-full h-1 group-hover:h-2 bg-white/20 transition-all relative">
            <div
              className="h-full bg-emerald-500 relative transition-[width] duration-75 ease-linear"
              style={{ width: `${Math.min(100, (currentTime / duration) * 100)}%` }}
            >
              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
