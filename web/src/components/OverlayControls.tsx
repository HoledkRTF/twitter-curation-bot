'use client';

import React, { useState } from 'react';
import { Heart, X, Volume2, VolumeX, ExternalLink } from 'lucide-react';
import { MediaItem } from '@/lib/types';

interface OverlayControlsProps {
  item: MediaItem;
  queueCount: number;
  isMuted: boolean;
  activeList?: string;
  onSwitchList?: (listNum: '1' | '2') => void;
  onToggleMute: () => void;
  onLike: () => void;
  onSkip: () => void;
}

export function OverlayControls({
  item,
  queueCount,
  isMuted,
  activeList,
  onSwitchList,
  onToggleMute,
  onLike,
  onSkip,
}: OverlayControlsProps) {
  const [expanded, setExpanded] = useState(false);

  // Extract author username safely from screen_name or tweet_url
  let author = item.screen_name;
  if (!author || author === 'unknown') {
    const parts = item.tweet_url?.split('/');
    if (parts && parts.length >= 4 && parts[3] !== 'unknown') {
      author = parts[3];
    }
  }
  const authorHandle = author && author !== 'unknown' ? `@${author}` : 'View Tweet';

  return (
    <div className="absolute inset-0 pointer-events-none z-30 flex flex-col justify-between p-4 md:p-6">
      {/* Top Bar */}
      <div className="flex justify-between items-center pointer-events-auto">
        {onSwitchList ? (
          <div className="flex items-center bg-black/60 backdrop-blur-md rounded-full p-1 border border-white/10 shadow-lg text-xs font-semibold">
            <button
              onClick={e => {
                e.stopPropagation();
                onSwitchList('1');
              }}
              className={`px-3 py-1 rounded-full transition-all ${
                activeList === '1'
                  ? 'bg-white text-black font-bold shadow'
                  : 'text-white/70 hover:text-white'
              }`}
            >
              List 1
            </button>
            <button
              onClick={e => {
                e.stopPropagation();
                onSwitchList('2');
              }}
              className={`px-3 py-1 rounded-full transition-all ${
                activeList === '2'
                  ? 'bg-white text-black font-bold shadow'
                  : 'text-white/70 hover:text-white'
              }`}
            >
              List 2
            </button>
          </div>
        ) : <div />}

        <button
          onClick={e => {
            e.stopPropagation();
            onToggleMute();
          }}
          className="p-3 bg-black/60 backdrop-blur-md rounded-full text-white/90 hover:bg-black/80 active:scale-95 transition-all border border-white/10 shadow-lg"
        >
          {isMuted ? <VolumeX className="w-5 h-5 text-red-400" /> : <Volume2 className="w-5 h-5 text-emerald-400" />}
        </button>
      </div>

      {/* Bottom Overlay & Controls */}
      <div className="flex flex-col gap-4 pointer-events-auto max-w-xl">
        {/* Caption & Metadata */}
        <div className="bg-gradient-to-t from-black/95 via-black/60 to-transparent p-4 rounded-2xl flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <a
              href={item.tweet_url}
              target="_blank"
              rel="noreferrer"
              onClick={e => e.stopPropagation()}
              className="text-sm font-bold text-sky-400 hover:underline flex items-center gap-1"
            >
              {authorHandle}
              <ExternalLink className="w-3.5 h-3.5 opacity-70" />
            </a>
            <span className="text-xs text-white/40">• {queueCount} left</span>
            {item.source_list_num && (
              <span className="text-xs text-white/40">• List {item.source_list_num}</span>
            )}
          </div>

          <p
            onClick={e => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
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
            onClick={e => {
              e.stopPropagation();
              onSkip();
            }}
            className="flex-1 max-w-[140px] py-3.5 px-6 bg-red-600/85 hover:bg-red-600 active:scale-90 transition-all rounded-full flex items-center justify-center gap-2 font-semibold text-white shadow-xl backdrop-blur-sm border border-red-500/30"
          >
            <X className="w-5 h-5" />
            Skip
          </button>

          <button
            onClick={e => {
              e.stopPropagation();
              onLike();
            }}
            className="flex-1 max-w-[140px] py-3.5 px-6 bg-emerald-600/85 hover:bg-emerald-600 active:scale-90 transition-all rounded-full flex items-center justify-center gap-2 font-semibold text-white shadow-xl backdrop-blur-sm border border-emerald-500/30"
          >
            <Heart className="w-5 h-5 fill-current" />
            Love
          </button>
        </div>
      </div>
    </div>
  );
}
