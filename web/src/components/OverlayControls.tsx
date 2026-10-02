'use client';

import React, { useState } from 'react';
import { Heart, X, Volume2, VolumeX, ExternalLink } from 'lucide-react';
import { MediaItem } from '@/lib/types';

interface OverlayControlsProps {
  item: MediaItem;
  queueCount: number;
  isMuted: boolean;
  onToggleMute: () => void;
  onLike: () => void;
  onSkip: () => void;
}

export function OverlayControls({
  item,
  queueCount,
  isMuted,
  onToggleMute,
  onLike,
  onSkip,
}: OverlayControlsProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="absolute inset-0 pointer-events-none z-30 flex flex-col justify-between p-4 md:p-6">
      {/* Top Bar */}
      <div className="flex justify-end pointer-events-auto">
        <button
          onClick={onToggleMute}
          className="p-3 bg-black/50 backdrop-blur-md rounded-full text-white/90 hover:bg-black/70 active:scale-95 transition-all border border-white/10"
        >
          {isMuted ? <VolumeX className="w-5 h-5 text-red-400" /> : <Volume2 className="w-5 h-5 text-emerald-400" />}
        </button>
      </div>

      {/* Bottom Overlay & Controls */}
      <div className="flex flex-col gap-4 pointer-events-auto max-w-xl">
        {/* Caption & Metadata */}
        <div className="bg-gradient-to-t from-black/90 via-black/50 to-transparent p-4 rounded-2xl flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <a
              href={item.tweet_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-bold text-sky-400 hover:underline flex items-center gap-1"
            >
              @{item.screen_name || 'author'}
              <ExternalLink className="w-3.5 h-3.5 opacity-70" />
            </a>
            <span className="text-xs text-white/40">• {queueCount} left</span>
          </div>

          <p
            onClick={() => setExpanded(!expanded)}
            className={`text-sm text-white/90 leading-snug cursor-pointer ${
              expanded ? '' : 'line-clamp-2'
            }`}
          >
            {item.text || 'No caption'}
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-center gap-6 pb-2">
          <button
            onClick={onSkip}
            className="flex-1 max-w-[140px] py-3.5 px-6 bg-red-600/80 hover:bg-red-600 active:scale-90 transition-all rounded-full flex items-center justify-center gap-2 font-semibold text-white shadow-lg backdrop-blur-sm border border-red-500/30"
          >
            <X className="w-5 h-5" />
            Skip
          </button>

          <button
            onClick={onLike}
            className="flex-1 max-w-[140px] py-3.5 px-6 bg-emerald-600/80 hover:bg-emerald-600 active:scale-90 transition-all rounded-full flex items-center justify-center gap-2 font-semibold text-white shadow-lg backdrop-blur-sm border border-emerald-500/30"
          >
            <Heart className="w-5 h-5 fill-current" />
            Love
          </button>
        </div>
      </div>
    </div>
  );
}
