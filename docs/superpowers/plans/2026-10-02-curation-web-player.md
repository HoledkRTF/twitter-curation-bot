# Full-Screen Curation Web Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-friendly, full-screen swipeable web video player deployed to Vercel that interfaces with the existing Apify KV store and Telegram Bot API to curate Twitter media directly to the user's private Telegram channel.

**Architecture:** A standalone Next.js App Router project located in `web/` with serverless API routes (`/api/queue` and `/api/action`). The frontend implements a pure-black full-viewport snap player with touch swipe and keyboard shortcuts, streaming video directly from Twitter's CDN.

**Tech Stack:** Next.js 14/15 (App Router, TypeScript), Tailwind CSS, Lucide React, `apify-client`, `node-fetch` / native `fetch`.

## Global Constraints
- Target location: `web/` within workspace `c:\Users\clint\.gemini\antigravity\scratch\goon-tools\twitter-curation-bot\web`
- Do not modify or break `bot.py` or existing Apify store records.
- All Twitter media URLs must stream via HTML5 `<video>` directly from `video.twimg.com`.
- Telegram actions must use Telegram Bot API (`sendVideo` / `sendPhoto`).

---

### Task 1: Web Project Scaffolding & Configuration

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tailwind.config.js`
- Create: `web/postcss.config.js`
- Create: `web/src/app/globals.css`
- Create: `web/.env.example`

**Interfaces:**
- Consumes: None
- Produces: Runnable Next.js environment with Tailwind CSS and types.

- [ ] **Step 1: Create `package.json` with required dependencies**

```json
{
  "name": "curation-web-player",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "apify-client": "^2.11.0",
    "lucide-react": "^1.16.0",
    "next": "14.2.15",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/node": "^20.14.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.4.5"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json` and Tailwind config**

`web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`web/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

`web/postcss.config.js`:
```javascript
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3: Create `web/src/app/globals.css` with dark full-screen styles**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background-color: #000000;
  color: #ffffff;
  overflow: hidden;
  user-select: none;
  -webkit-user-select: none;
}
```

- [ ] **Step 4: Create `.env.example`**

```env
APIFY_API_TOKEN=your_apify_api_token
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHANNEL_ID=your_telegram_channel_id
```

- [ ] **Step 5: Install dependencies and verify build**

Run: `cd web && npm install`  
Expected: `added N packages` with exit code 0.

- [ ] **Step 6: Commit scaffolding**

```bash
git add web/package.json web/tsconfig.json web/tailwind.config.js web/postcss.config.js web/src/app/globals.css web/.env.example
git commit -m "chore(web): scaffold next.js full-screen player project"
```

---

### Task 2: Serverless API Routes (Apify & Telegram Sync)

**Files:**
- Create: `web/src/lib/types.ts`
- Create: `web/src/lib/apify.ts`
- Create: `web/src/app/api/queue/route.ts`
- Create: `web/src/app/api/action/route.ts`

**Interfaces:**
- Consumes: Environment variables (`APIFY_API_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`)
- Produces:
  - `GET /api/queue` -> `{ queue: MediaItem[], stats: BotStats, mediaFilter: string }`
  - `POST /api/action` -> `{ success: boolean, remainingCount: number }`

- [ ] **Step 1: Define `web/src/lib/types.ts`**

```typescript
export interface MediaItem {
  tweet_url: string;
  text: string;
  screen_name?: string;
  type: 'video' | 'photo';
  url: string;
  urls?: string[];
  width?: number;
  height?: number;
  duration_millis?: number;
}

export interface BotStats {
  loved: number;
  skipped: number;
}
```

- [ ] **Step 2: Create Apify client helper in `web/src/lib/apify.ts`**

```typescript
import { ApifyClient } from 'apify-client';

const token = process.env.APIFY_API_TOKEN || '';
export const apifyClient = new ApifyClient({ token });

export async function getStoreClient() {
  const store = await apifyClient.keyValueStores().getOrCreate('twitter-curation-bot-storage');
  return apifyClient.keyValueStore(store.id);
}
```

- [ ] **Step 3: Implement `GET /api/queue/route.ts`**

```typescript
import { NextResponse } from 'next/server';
import { getStoreClient } from '@/lib/apify';
import { MediaItem, BotStats } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const store = await getStoreClient();
    const [qRec, sRec, fRec] = await Promise.all([
      store.getRecord('queue'),
      store.getRecord('bot_stats'),
      store.getRecord('media_filter'),
    ]);

    const queue = (qRec?.value as MediaItem[]) || [];
    const stats = (sRec?.value as BotStats) || { loved: 0, skipped: 0 };
    const mediaFilter = (fRec?.value as string) || 'all';

    return NextResponse.json({ queue, stats, mediaFilter });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
```

- [ ] **Step 4: Implement `POST /api/action/route.ts` with Telegram forwarding**

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { getStoreClient } from '@/lib/apify';
import { MediaItem, BotStats } from '@/lib/types';

export async function POST(req: NextRequest) {
  try {
    const { action, tweetUrl } = await req.json();
    if (!action || !tweetUrl) {
      return NextResponse.json({ error: 'Missing action or tweetUrl' }, { status: 400 });
    }

    const store = await getStoreClient();
    const [qRec, sRec] = await Promise.all([
      store.getRecord('queue'),
      store.getRecord('bot_stats'),
    ]);

    let queue = (qRec?.value as MediaItem[]) || [];
    let stats = (sRec?.value as BotStats) || { loved: 0, skipped: 0 };

    const itemIndex = queue.findIndex(item => item.tweet_url === tweetUrl);
    if (itemIndex === -1) {
      return NextResponse.json({ error: 'Item not found in queue' }, { status: 404 });
    }

    const item = queue[itemIndex];

    if (action === 'like') {
      stats.loved = (stats.loved || 0) + 1;
      
      const botToken = process.env.TELEGRAM_BOT_TOKEN;
      const channelId = process.env.TELEGRAM_CHANNEL_ID;
      
      if (botToken && channelId) {
        const caption = `${item.text}\n\n<a href="${item.tweet_url}">@${item.screen_name || 'author'}</a>`;
        const method = item.type === 'photo' ? 'sendPhoto' : 'sendVideo';
        const mediaParam = item.type === 'photo' ? 'photo' : 'video';
        
        await fetch(`https://api.telegram.org/bot${botToken}/${method}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: channelId,
            [mediaParam]: item.url,
            caption,
            parse_mode: 'HTML',
          }),
        });
      }
    } else if (action === 'skip') {
      stats.skipped = (stats.skipped || 0) + 1;
    }

    queue.splice(itemIndex, 1);

    await Promise.all([
      store.setRecord({ key: 'queue', value: queue }),
      store.setRecord({ key: 'bot_stats', value: stats }),
    ]);

    return NextResponse.json({ success: true, remainingCount: queue.length });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
```

- [ ] **Step 5: Commit API routes**

```bash
git add web/src/lib/types.ts web/src/lib/apify.ts web/src/app/api/
git commit -m "feat(web): implement serverless API routes for queue and curation actions"
```

---

### Task 3: Full-Screen Video & Photo Media Components

**Files:**
- Create: `web/src/components/MediaSlide.tsx`
- Create: `web/src/components/OverlayControls.tsx`

**Interfaces:**
- Consumes: `MediaItem`, `onLike`, `onSkip`, `isMuted`, `onToggleMute`
- Produces: Fullscreen interactive video player with resolution/duration badge.

- [ ] **Step 1: Implement `web/src/components/MediaSlide.tsx`**

```tsx
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
```

- [ ] **Step 2: Implement `web/src/components/OverlayControls.tsx`**

```tsx
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
```

- [ ] **Step 3: Commit media and overlay components**

```bash
git add web/src/components/
git commit -m "feat(web): add MediaSlide and OverlayControls with audio and action handlers"
```

---

### Task 4: Keyboard Shortcuts & Touch Swipe Container

**Files:**
- Create: `web/src/components/SwipeContainer.tsx`

**Interfaces:**
- Consumes: Array of `MediaItem`, current index, action callbacks.
- Produces: Touch gesture detection and keyboard event dispatching.

- [ ] **Step 1: Implement `web/src/components/SwipeContainer.tsx`**

```tsx
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
```

- [ ] **Step 2: Commit SwipeContainer component**

```bash
git add web/src/components/SwipeContainer.tsx
git commit -m "feat(web): add gesture swipe detection and desktop keyboard shortcuts"
```

---

### Task 5: Main Page & Deployment Config

**Files:**
- Create: `web/src/app/page.tsx`
- Create: `web/src/app/layout.tsx`
- Create: `web/vercel.json`

**Interfaces:**
- Consumes: `/api/queue`, `/api/action`, `SwipeContainer`
- Produces: Complete Next.js entrypoint and Vercel build definition.

- [ ] **Step 1: Implement `web/src/app/layout.tsx`**

```tsx
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Curation Web Player',
  description: 'Full-screen continuous media curation player',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-black text-white select-none">{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: Implement `web/src/app/page.tsx`**

```tsx
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
```

- [ ] **Step 3: Create `web/vercel.json`**

```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build"
}
```

- [ ] **Step 4: Build test verification**

Run: `cd web && npm run build`  
Expected: Next.js production build succeeds with 0 errors.

- [ ] **Step 5: Commit complete web application**

```bash
git add web/
git commit -m "feat(web): finalize full-screen curation player with Vercel deployment config"
```
