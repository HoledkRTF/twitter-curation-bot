# Multi-Photo Albums Design Specification

**Date:** 2026-10-08  
**Target:** Telegram Bot & Web Curation Player  
**Feature:** Multi-Photo Album Support (Grouping, Reviewing, Channel Publishing)  

---

## 1. Overview & Goals
Currently, when a tweet contains multiple photos (2 to 4 photos in a Twitter gallery), the scraper breaks each photo into a separate queue item. This causes:
- Fragmented curation: photos from the same set are reviewed out of context as individual single-image posts.
- Redundant channel posts: loving each photo sends disjointed single-photo messages instead of a unified Telegram photo album.
- Unclean captions: Twitter auto-appends trailing `https://t.co/...` attachment links to tweet text.

The goal is to bundle multi-photo tweets into unified album items across both Telegram and the web player, ensuring users can review the complete set together and publish all photos as a single Telegram media group when loved.

---

## 2. Architecture & Data Flow

```
   [ Twitter GraphQL API ]
              │
              ▼
   [ bot.py Scraper ] ─── Group photos per tweet & strip trailing media t.co links
              │
              ├───► Single photo / video: Native send_photo / send_video with inline buttons
              │
              ├───► Multi-photo album in Telegram:
              │       1. send_media_group (all photos bundled in Twitter-like grid)
              │       2. Action control message (❤️ Love / 👎 Skip / ⏸️ Pause)
              │       3. On Love: send_media_group to Destination Channel
              │
              ▼
   [ Apify KV Store (queue) ]
              │
              ▼
   [ Web Player (goon-swipe.vercel.app) ]
              ├───► Multi-photo carousel with dot indicators (• • •) & tap/arrow navigation
              └───► On Love: POST /api/action -> Telegram Bot API sendMediaGroup to Channel
```

---

## 3. Data Model Changes

In both Python (`bot.py`) and TypeScript (`web/src/lib/types.ts`):

```typescript
export interface MediaItem {
  tweet_url: string;
  text: string;
  screen_name: string;
  type: 'video' | 'photo' | 'album';
  url: string;             // Primary/first photo or video URL (backward compatibility)
  urls?: string[];         // All photo URLs if album, or video bitrate variants
  width?: number;
  height?: number;
  duration_millis?: number;
  source_list?: string;
  source_list_num?: string;
}
```

---

## 4. Scraper Logic (`bot.py`)

1. **Caption Sanitization:**
   Twitter appends trailing `https://t.co/...` URLs for attached media. Before creating `media_obj`, regex-clean the trailing media link from `tweet_text`:
   `re.sub(r'https://t\.co/[a-zA-Z0-9]+$', '', tweet_text).strip()`
2. **Media Grouping:**
   - Scan `tweet.get('extended_entities', {}).get('media', [])`.
   - If media contains multiple `photo` items (e.g. 2 to 4 photos):
     - Create a single `media_obj` with:
       - `type: 'album'`
       - `urls: [m['media_url_https'] for m in media if m.get('type') == 'photo']`
       - `url: urls[0]`
     - Store in `extracted_items` as one atomic item.
   - If media contains a single photo, keep `type: 'photo'`.
   - If media contains video, keep `type: 'video'` with bitrate variant list.
3. **Deduplication:**
   - Deduplicate items against `history` using `item['url']` and `item['tweet_url']`.

---

## 5. Telegram Bot Flow (`bot.py`)

### Reviewing an Item (`send_next_tweet`)
- **Single photo / video:** Retain existing behavior.
- **Album (`type == 'album'`):**
  1. Build `InputMediaPhoto` list for all URLs in `item['urls']`. Attach full formatted caption (`caption`) to the first media element.
  2. Send album via `await context.bot.send_media_group(chat_id=chat_id, media=input_media_list)`.
  3. Send a follow-up action control message:
     - Text: `📸 Album (X photos) • Review controls:`
     - Inline keyboard: `[❤️ Love (Save to Channel)] [👎 Skip]` / `[⏸️ Pause]`
  4. Associate `msg.message_id` with `item` in `review_dict`.

### Action Handling (`button_handler`)
- **On Love (`query.data == 'like'`):**
  - If `item.get('type') == 'album'`:
    - Send all photos as a media group to `TELEGRAM_CHANNEL_ID` via `send_media_group`.
  - Else:
    - Send single photo/video to `TELEGRAM_CHANNEL_ID`.
  - Update stats, edit review message to `[SAVED TO CHANNEL]`, and load next tweet.
- **On Skip (`query.data == 'skip'`):**
  - Edit review message to `[SKIPPED]`, update stats, and load next tweet.

---

## 6. Web Player Flow (`web/`)

### Frontend (`MediaSlide.tsx` & `SwipeContainer.tsx`)
- When `item.type === 'album'` or `item.urls && item.urls.length > 1`:
  - Display current photo with smooth transitions.
  - Render pagination pill / dots at the top (e.g. `1 / 4` with dots `• • • •`).
  - Left / Right tap zones or arrow buttons allow browsing through album photos.
  - Up/Down swipe advances to next/previous card in queue without interfering with album navigation.

### API Route (`/api/action/route.ts`)
- In `handleLove`:
  - If `item.type === 'album'` and `item.urls && item.urls.length > 1`:
    - Use Telegram Bot API `sendMediaGroup` to publish all photos together to `TELEGRAM_CHANNEL_ID` with caption on first photo.
  - Else:
    - Use existing `sendPhoto` or `sendVideo`.

---

## 7. Verification & Testing

1. Python syntax check (`python -m py_compile bot.py`).
2. Next.js production build check (`npm run build` inside `web/`).
3. Deploy bot to Render and web app to Vercel.
4. Verify multi-photo tweet from List 2 scrapes as a single album, sends as a media group, and publishes all photos to the channel.
