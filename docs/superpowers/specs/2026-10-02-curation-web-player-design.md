# Full-Screen Curation Web Player Design Specification

**Date:** 2026-10-02  
**Target:** Companion Web Application for Twitter Curation Bot  
**Stack:** Next.js (App Router), Tailwind CSS, Lucide React, Apify Client, Telegram Bot API  

---

## 1. Overview & Goals
The goal of this project is to provide a fast, full-screen, mobile-friendly web companion (Tinder/TikTok-style) for curating queued Twitter media directly to the user's private Telegram channel. 

Key objectives:
- Full-screen immersion with zero lag, instant video looping, and touch/keyboard navigation.
- Shared state with the existing Telegram bot via the Apify Key-Value store (`twitter-curation-bot-storage`).
- Zero cold starts by deploying on Vercel's global edge network.
- Complete isolation: Does not touch or destabilize existing `bot.py` code.

---

## 2. Architecture & Data Flow

```
+-----------------------------------------------------------+
|                   Vercel Deployment                       |
|                                                           |
|  +--------------------+        +-----------------------+  |
|  | Frontend Player UI | <----> | Serverless API Routes |  |
|  +--------------------+        +-----------------------+  |
+----------------------------------------|------------------+
                                         |
                       +-----------------+-----------------+
                       |                                   |
                       v                                   v
             [ Apify KV Store ]                 [ Telegram Bot API ]
         (twitter-curation-bot-storage)       (sendVideo to Channel)
```

### Shared Data Model
The web app uses the existing Apify KV records:
- `queue`: Array of media items waiting for review.
- `media_filter`: Active filter (`"all"`, `"video"`, `"photo"`).
- `bot_stats`: Object containing `{"loved": number, "skipped": number}`.

Each queue item conforms to:
```json
{
  "tweet_url": "https://vxtwitter.com/username/status/123456",
  "text": "Caption text",
  "screen_name": "username",
  "type": "video",
  "url": "https://video.twimg.com/...mp4",
  "urls": ["https://video.twimg.com/...high.mp4", "https://video.twimg.com/...med.mp4"],
  "width": 1920,
  "height": 1080,
  "duration_millis": 45000
}
```

---

## 3. Serverless API Endpoints

### `GET /api/queue`
- Fetches the latest queue from Apify KV Store.
- Filters items according to `media_filter` (or returns all if `"all"`).
- Returns `{ queue, stats, media_filter }`.

### `POST /api/action`
- Payload: `{ action: "like" | "skip", tweetUrl: string }`.
- Logic:
  1. Finds the matching item in `queue` by `tweetUrl`.
  2. If `action === "like"`:
     - Sends the video/photo to `TELEGRAM_CHANNEL_ID` via `https://api.telegram.org/bot<TOKEN>/sendVideo` or `sendPhoto`.
     - Includes caption with creator `@username` and original tweet link.
     - Increments `bot_stats.loved`.
  3. If `action === "skip"`:
     - Increments `bot_stats.skipped`.
  4. Removes the item from `queue`.
  5. Updates `queue` and `bot_stats` in Apify KV Store.
  6. Returns `{ success: true, remainingCount: queue.length }`.

---

## 4. Frontend UX & Interactions

### Layout
- 100vh / 100dvh full viewport container with pure black background (`#000`).
- Vertical snap container (CSS scroll snap or swipe physics) displaying one media item at a time.
- Direct video streaming from `video.twimg.com` with `<video playsinline loop preload="auto">`.

### Controls & Gestures
1. **Mobile Touch:**
   - **Swipe Right:** Love (action triggers, green haptic feedback overlay, forwards to Telegram channel, moves to next).
   - **Swipe Left:** Skip (action triggers, red dismiss animation, moves to next).
   - **Swipe Up / Down:** Next / Previous clip in current buffer.
   - **Tap Screen:** Play / Pause toggle.
   - **Mute Icon:** Toggle global sound on/off (persisted in localStorage).

2. **Desktop Keyboard:**
   - **Right Arrow (`→`):** Love & advance.
   - **Left Arrow (`←`):** Skip & advance.
   - **Down Arrow (`↓`) / Space:** Play/Pause or advance.
   - **Up Arrow (`↑`):** Previous clip.
   - **M key:** Toggle mute.

3. **On-Screen Overlays:**
   - **Top Badge:** `⏱️ 1:24 • 1080p` (duration + resolution).
   - **Bottom Meta:** `@creator` handle, expandable caption, and queue count badge (`38 left`).
   - **Bottom Quick Buttons:** Floating `[ 👎 Skip ]` and `[ ❤️ Love ]` for effortless one-thumb tapping.

---

## 5. Security & Environment Configuration
Environment variables needed on Vercel:
- `APIFY_API_TOKEN`: Access to Apify KV Store.
- `TELEGRAM_BOT_TOKEN`: To push loved videos to the channel.
- `TELEGRAM_CHANNEL_ID`: Destination channel.
- `ACCESS_PASSWORD` (Optional): Simple passcode protection on the web page so unauthorized users cannot curate or deplete the queue.

---

## 6. Testing & Rollout Strategy
1. Scaffold Next.js application in `curation-web-player/`.
2. Implement and test local endpoints against Apify store and Telegram API.
3. Verify video CORS streaming and mobile touch gestures in browser.
4. Deploy to Vercel and verify live bidirectional queue sync with Telegram bot.
