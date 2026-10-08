# Multi-Photo Albums Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group multi-photo tweets into unified albums across Telegram and the web player so all photos are reviewed together and saved to the channel as a single media group.

**Architecture:** Update Twitter GraphQL scraper in `bot.py` to bundle multi-photo tweets into a single `album` item, clean trailing media t.co links, deliver as a Telegram `send_media_group` with companion review controls, and support swipeable image carousels in the Next.js web player with atomic multi-photo publishing to Telegram.

**Tech Stack:** Python 3 (python-telegram-bot, httpx), TypeScript, Next.js 14, Tailwind CSS, Apify KV Store.

## Global Constraints
- Preserve backward compatibility for single photo and video queue items.
- Retain existing `url` field pointing to the primary photo so legacy clients do not break.
- Avoid external dependencies; use existing libraries.
- Zero TypeScript errors and successful `npm run build` verification.

---

### Task 1: Scraper & Telegram Bot Multi-Photo Album Support (`bot.py`)

**Files:**
- Modify: `bot.py`

**Interfaces:**
- Produces: `MediaItem` with `type: 'album'`, `urls: string[]`, `url: string`, and cleaned `text` without trailing media link.
- Telegram Delivery: `send_media_group` for multi-photo albums with follow-up action control message, and `send_media_group` to channel on Love.

- [ ] **Step 1: Sanitize trailing media `t.co` URLs from tweet text**
Clean trailing media URLs in `extract_media_from_twitter` using regex:
`tweet_text = re.sub(r'\s*https://t\.co/[a-zA-Z0-9]+$', '', tweet_text).strip()`

- [ ] **Step 2: Group multi-photo tweets into atomic album items**
In `extract_media_from_twitter`, check photos in `media`:
If more than 1 photo exists:
`media_obj = {'tweet_url': tweet_url, 'text': tweet_text, 'screen_name': screen_name, 'type': 'album', 'urls': photo_urls, 'url': photo_urls[0]}`
If 1 photo exists: keep `type: 'photo'`.
If video exists: keep `type: 'video'`.

- [ ] **Step 3: Update `send_next_tweet` for albums**
If `next_item['type'] == 'album'`:
Download or pass media URLs as `InputMediaPhoto`, send album with caption on first photo via `send_media_group`.
Send action control message with `❤️ Love`, `👎 Skip`, `⏸️ Pause` and record in `review_dict`.

- [ ] **Step 4: Update `button_handler` for albums on Love**
When user clicks `like`:
If `item.get('type') == 'album'` and `item.get('urls')`:
Send all photos as a media group to `TELEGRAM_CHANNEL_ID`.
Else send single photo/video.

- [ ] **Step 5: Verify Python syntax**
Run `python -m py_compile bot.py`.

- [ ] **Step 6: Commit changes**
`git add bot.py`
`git commit -m "feat(bot): support multi-photo album scraping and telegram media groups"`

---

### Task 2: Web Player Backend Action Support (`web/`)

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/app/api/action/route.ts`

**Interfaces:**
- Consumes: `MediaItem` with `type: 'album'` and `urls?: string[]`.
- Produces: Telegram Bot API `sendMediaGroup` call in `/api/action` when loving an album.

- [ ] **Step 1: Update TypeScript types**
In `web/src/lib/types.ts`, update `type`: `'video' | 'photo' | 'album'`.

- [ ] **Step 2: Update `/api/action` route for albums**
In `web/src/app/api/action/route.ts`:
If `item.type === 'album'` and `item.urls && item.urls.length > 1`:
Build `media` payload with `InputMediaPhoto` objects, set caption on the first photo, and call `https://api.telegram.org/bot<TOKEN>/sendMediaGroup`.

- [ ] **Step 3: Verify TypeScript compilation**
Run `npx tsc --noEmit` inside `web/`.

- [ ] **Step 4: Commit changes**
`git add web/src/lib/types.ts web/src/app/api/action/route.ts`
`git commit -m "feat(web): add sendMediaGroup support for albums in action route"`

---

### Task 3: Web Player Frontend Multi-Photo Carousel (`web/`)

**Files:**
- Modify: `web/src/components/MediaSlide.tsx`
- Modify: `web/src/components/OverlayControls.tsx`
- Modify: `web/src/components/SwipeContainer.tsx`

**Interfaces:**
- Consumes: `item.urls` and `item.type === 'album'`.
- Produces: Sub-index navigation, photo indicator dots (`• • •`), and album badge.

- [ ] **Step 1: Update `MediaSlide.tsx` for album carousels**
Add internal image index state and left/right tap or arrow buttons to cycle through photos in `item.urls`.
Show pagination dots at bottom of image.

- [ ] **Step 2: Update `OverlayControls.tsx` for album badge**
If `item.type === 'album'` or `item.urls.length > 1`, display badge (e.g. `📸 1/3`).

- [ ] **Step 3: Run production build verification**
Run `npm run build` inside `web/` to ensure zero compilation or lint errors.

- [ ] **Step 4: Commit changes**
`git add web/src/components/`
`git commit -m "feat(web): add multi-photo album carousel and indicator controls"`

---

### Task 4: Deployment & Verification

**Files:**
- Modify: `.agents/AGENTS.md`

- [ ] **Step 1: Assign Codename & update `.agents/AGENTS.md`**
Assign memorable codename (e.g., `Opal-Gallery` v1.13.0), update rolling list to 5 items in `.agents/AGENTS.md`.

- [ ] **Step 2: Create Git tag & Push**
`git tag Opal-Gallery`
`git push origin main --tags`

- [ ] **Step 3: Verify Live Deployments**
Verify Render deploy and Vercel aliases.
