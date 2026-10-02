import json
import os
import html
import asyncio
import httpx
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apify_client import ApifyClient

# Config from environment variables
config = {
    'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'telegram_channel_id': os.environ.get('TELEGRAM_CHANNEL_ID', ''),
    'twitter_list_url': os.environ.get('TWITTER_LIST_URL', ''),
    'apify_api_token': os.environ.get('APIFY_API_TOKEN', ''),
    'twitter_auth_token': os.environ.get('TWITTER_AUTH_TOKEN', ''),
    'twitter_ct0': os.environ.get('TWITTER_CT0', '')
}

PORT = int(os.environ.get('PORT', 10000))
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', '')

apify_client = ApifyClient(config['apify_api_token'])

# Initialize persistent storage on Apify to survive Render sleep cycles
try:
    store = apify_client.key_value_stores().get_or_create(name='twitter-curation-bot-storage')
    store_client = apify_client.key_value_store(store.id)
except Exception as e:
    print(f"Failed to connect to Apify KV Store: {e}")
    store_client = None

def load_data():
    tweet_queue = []
    history = []
    unreviewed_count = 0
    media_filter = "all"
    custom_cookies = {}
    include_retweets = False
    custom_list_url = ""
    bot_stats = {"loved": 0, "skipped": 0}
    
    if store_client:
        q_rec = store_client.get_record("queue")
        if q_rec and q_rec.get('value'):
            tweet_queue = q_rec['value']
            
        h_rec = store_client.get_record("history")
        if h_rec and h_rec.get('value'):
            history = h_rec['value']
            
        u_rec = store_client.get_record("unreviewed_count")
        if u_rec and u_rec.get('value') is not None:
            unreviewed_count = u_rec['value']
            
        f_rec = store_client.get_record("media_filter")
        if f_rec and f_rec.get('value'):
            media_filter = f_rec['value']
            
        c_rec = store_client.get_record("custom_cookies")
        if c_rec and c_rec.get('value'):
            custom_cookies = c_rec['value']
            
        r_rec = store_client.get_record("include_retweets")
        if r_rec and r_rec.get('value') is not None:
            include_retweets = r_rec['value']
            
        l_rec = store_client.get_record("custom_list_url")
        if l_rec and l_rec.get('value'):
            custom_list_url = l_rec['value']
            
        s_rec = store_client.get_record("bot_stats")
        if s_rec and s_rec.get('value'):
            bot_stats = s_rec['value']
            
    return tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats

def save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys=None):
    if store_client:
        if keys is None:
            keys = {"queue", "history", "unreviewed_count", "media_filter", "custom_cookies", "include_retweets", "custom_list_url", "bot_stats"}
        if "queue" in keys:
            store_client.set_record("queue", tweet_queue)
        if "history" in keys:
            store_client.set_record("history", history)
        if "unreviewed_count" in keys:
            store_client.set_record("unreviewed_count", unreviewed_count)
        if "media_filter" in keys:
            store_client.set_record("media_filter", media_filter)
        if "custom_cookies" in keys:
            store_client.set_record("custom_cookies", custom_cookies)
        if "include_retweets" in keys:
            store_client.set_record("include_retweets", include_retweets)
        if "custom_list_url" in keys:
            store_client.set_record("custom_list_url", custom_list_url)
        if "bot_stats" in keys:
            store_client.set_record("bot_stats", bot_stats)

tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats = load_data()
review_dict = {}  # Maps message_id -> item for /undo
last_skipped = None

async def extract_media_from_twitter(list_id):
    extracted_items = []
    
    active_ct0 = custom_cookies.get('ct0') or config['twitter_ct0']
    active_auth_token = custom_cookies.get('auth_token') or config['twitter_auth_token']
    
    headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": active_ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    
    cookies = {
        "auth_token": active_auth_token,
        "ct0": active_ct0
    }
    
    # Known queryId for ListLatestTweetsTimeline
    query_id = "1LE3u14FJjPZUHKFGzos2g"
    url = f"https://x.com/i/api/graphql/{query_id}/ListLatestTweetsTimeline"
    
    variables = {"listId": list_id, "count": 100}
    features = {
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "tweetypie_unmention_optimization_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": False,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_media_download_video_enabled": False,
        "responsive_web_enhance_cards_enabled": False
    }

    cursor = None
    
    client = get_http_client()
    # Loop through pages to gather enough media
    for _ in range(10): # Fetch up to 10 pages
        if cursor:
            variables["cursor"] = cursor
        
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features),
        }
        
        try:
            res = await client.get(url, headers=headers, cookies=cookies, params=params, timeout=30.0)
            if res.status_code != 200:
                err_text = res.text[:200]
                print(f"Twitter API Error: {res.status_code} - {err_text}")
                if res.status_code in [401, 403] or "auth" in err_text.lower():
                    raise Exception("⚠️ Twitter cookies (auth_token or ct0) are invalid or have expired! Please update them in Render.")
                break
                
            data = res.json()
            instructions = data.get('data', {}).get('list', {}).get('tweets_timeline', {}).get('timeline', {}).get('instructions', [])
                
            new_cursor = None
            for inst in instructions:
                if inst.get('type') == 'TimelineAddEntries':
                    for entry in inst.get('entries', []):
                        content = entry.get('content', {})
                        
                        # Extract Next Page Cursor
                        if content.get('entryType') == 'TimelineTimelineCursor' and content.get('cursorType') == 'Bottom':
                            new_cursor = content.get('value')
                            
                        # Extract Tweet Data
                        if content.get('entryType') == 'TimelineTimelineItem':
                            result = content.get('itemContent', {}).get('tweet_results', {}).get('result', {})
                            tweet = result.get('legacy', {})
                            core = result.get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {})
                            screen_name = core.get('screen_name', 'unknown')
                            tweet_id = tweet.get('id_str', '')
                            tweet_url = f"https://vxtwitter.com/{screen_name}/status/{tweet_id}"
                            tweet_text = tweet.get('full_text', '')
                            
                            if 'retweeted_status_result' in tweet and not include_retweets:
                                continue # Skip retweets unless /rt on is set
                                
                            media = tweet.get('extended_entities', {}).get('media', [])
                            
                            for m in media:
                                media_obj = {'tweet_url': tweet_url, 'text': tweet_text, 'screen_name': screen_name}
                                original_info = m.get('original_info', {})
                                if original_info.get('width') and original_info.get('height'):
                                    media_obj['width'] = original_info['width']
                                    media_obj['height'] = original_info['height']
                                    
                                if m.get('type') in ['video', 'animated_gif']:
                                    v_info = m.get('video_info', {})
                                    if v_info.get('duration_millis'):
                                        media_obj['duration_millis'] = v_info['duration_millis']
                                    variants = v_info.get('variants', [])
                                    mp4s = [v for v in variants if v.get('content_type') == 'video/mp4']
                                    if mp4s:
                                        sorted_mp4s = sorted(mp4s, key=lambda x: x.get('bitrate', 0), reverse=True)
                                        media_obj['urls'] = [v['url'] for v in sorted_mp4s]
                                        media_obj['url'] = sorted_mp4s[0]['url'] # Keep primary for backwards compatibility
                                        media_obj['type'] = 'video'
                                        extracted_items.append(media_obj)
                                elif m.get('type') == 'photo':
                                    media_obj['url'] = m['media_url_https']
                                    media_obj['type'] = 'photo'
                                    extracted_items.append(media_obj)
                                        
            # If we didn't get a new cursor, or we have 500+ items, stop paginating
            if not new_cursor or len(extracted_items) >= 500:
                break
            cursor = new_cursor
            
            # Small delay to avoid rate limits
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error making GraphQL request: {e}")
            if "cookies" in str(e).lower() or "expired" in str(e).lower():
                raise e
                break
                
    return extracted_items

async def do_scrape(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    global tweet_queue, history, unreviewed_count
    await context.bot.send_message(chat_id=chat_id, text="🔄 Scraping Twitter list...")
    
    try:
        active_ct0 = custom_cookies.get('ct0') or config['twitter_ct0']
        active_auth_token = custom_cookies.get('auth_token') or config['twitter_auth_token']
        if not active_auth_token or not active_ct0:
            await context.bot.send_message(chat_id=chat_id, text="Error: Missing Twitter cookies! Use /setcookies <auth_token> <ct0>")
            return
            
        # Extract numeric list ID from URL like https://x.com/i/lists/2078086710118715619
        active_url = custom_list_url if custom_list_url else config['twitter_list_url']
        if not active_url:
            await context.bot.send_message(chat_id=chat_id, text="Error: No Twitter list URL configured!")
            return
            
        list_id = active_url.rstrip('/').split('/')[-1]
        items = await extract_media_from_twitter(list_id)
        
        count = 0
        added_items = []
        
        # Optimize O(N^2) list scan to O(1) lookups
        history_set = set(history)
        queue_urls = {q.get('url') for q in tweet_queue}
        
        for item in items:
            url = item['url']
            if url not in history_set and url not in queue_urls:
                added_items.append(item)
                history.append(url)
                history_set.add(url)
                count += 1
                
        # Prepend new items so the freshest media is served first
        tweet_queue = added_items + tweet_queue
        
        # Prevent history from growing infinitely and crashing memory
        if len(history) > 8000:
            history = history[-8000:]
        
        save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Scraped {len(items)} posts, found {count} brand new ones! Total in queue: {len(tweet_queue)}")
    except Exception as e:
        if "cookies" in str(e).lower() or "expired" in str(e).lower():
            await context.bot.send_message(chat_id=chat_id, text=f"{e}")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Error scraping: {e}")

async def scrape_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_scrape(context, update.message.chat_id)
    if tweet_queue:
        await send_next_tweet(update.message.chat_id, context)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count
    history.clear()
    unreviewed_count = 0
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats)
    await update.message.reply_text("🗑️ History cleared! The scraper will now re-fetch older tweets as if they were brand new.")

# Reuse TCP connections
_http_client = None

def get_http_client():
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=180.0)
    return _http_client

async def fetch_media_to_temp(url, type_='video'):
    suffix = '.mp4' if type_ == 'video' else '.jpg'
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    
    client = get_http_client()
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(path, 'wb') as f:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                f.write(chunk)
    return path

async def upload_to_gofile(filepath, filename="video.mp4"):
    client = get_http_client()
    res = await client.get("https://api.gofile.io/servers")
    server = res.json()['data']['servers'][0]['name']
    
    with open(filepath, 'rb') as f:
        files = {'file': (filename, f)}
        upload_res = await client.post(f"https://{server}.gofile.io/contents/uploadfile", files=files)
        
    return upload_res.json()['data']['downloadPage']

VERSION = "v1.11.0"

async def send_next_tweet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not tweet_queue:
        await do_scrape(context, chat_id)
        if not tweet_queue:
            await context.bot.send_message(chat_id=chat_id, text="Still empty! Try scraping again later when the Twitter list has new posts.")
            return False

    global unreviewed_count
    
    match_index = -1
    for i, item in enumerate(tweet_queue):
        if media_filter == "all":
            match_index = i
            break
        elif media_filter == "video" and item.get('type') == 'video':
            match_index = i
            break
        elif media_filter == "photo" and item.get('type') == 'photo':
            match_index = i
            break
            
    if match_index == -1:
        f_type = "videos" if media_filter == "video" else "photos"
        await context.bot.send_message(chat_id=chat_id, text=f"No {f_type} left in the queue! They might have been filtered out. Try changing the filter with /fa or run /scrape.")
        return False

    next_item = tweet_queue.pop(match_index)
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue"})
    
    keyboard = [
        [
            InlineKeyboardButton("❤️ Love (Save to Channel)", callback_data="like"),
            InlineKeyboardButton("👎 Skip", callback_data="skip")
        ],
        [
            InlineKeyboardButton("⏸️ Pause", callback_data="pause")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Video duration and resolution badge
    badge_parts = []
    duration_ms = next_item.get('duration_millis')
    if duration_ms:
        total_sec = round(duration_ms / 1000)
        mins = total_sec // 60
        secs = total_sec % 60
        badge_parts.append(f"⏱️ {mins}:{secs:02d}")
        
    w = next_item.get('width')
    h = next_item.get('height')
    if w and h and next_item.get('type') == 'video':
        badge_parts.append(f"{min(w, h)}p")
        
    badge_header = f"<b>{' • '.join(badge_parts)}</b>\n\n" if badge_parts else ""
    
    # Creator username directly on link
    author = next_item.get('screen_name')
    if not author or author == 'unknown':
        parts = next_item.get('tweet_url', '').split('/')
        if len(parts) >= 4 and parts[3] not in ('', 'unknown'):
            author = parts[3]
    author_label = f"@{author}" if author and author != 'unknown' else "Link to Tweet"

    safe_text = html.escape(next_item['text'][:800])
    caption = f"{badge_header}{safe_text}\n\n<a href='{next_item['tweet_url']}'>{author_label}</a>\n\n<code>{VERSION}</code>"
    
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Loading next item...")
    temp_path = None
    try:
        urls_to_try = next_item.get('urls', [next_item['url']])
        
        temp_path = await fetch_media_to_temp(urls_to_try[0], next_item['type'])
        file_size = os.path.getsize(temp_path)
        
        if file_size > 50_000_000:
            await status_msg.edit_text("Uploading full-res to Gofile (too large for Telegram)...")
            try:
                gofile_link = await upload_to_gofile(temp_path)
                caption += f"\n\n⚠️ <b>DOWNSCALED PREVIEW</b> (Original exceeds Telegram's 50MB limit)\n📥 <a href='{gofile_link}'>Download Full-Res (Gofile)</a>"
            except Exception as e:
                print(f"Gofile upload failed: {e}")
                caption += f"\n\n⚠️ <b>DOWNSCALED PREVIEW</b> (Original exceeds Telegram's 50MB limit, Gofile upload failed)"
                
            # Try to fetch smaller variants until one is < 50MB
            success_downscale = False
            for u in urls_to_try[1:]:
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                    temp_path = await fetch_media_to_temp(u, next_item['type'])
                    if os.path.getsize(temp_path) <= 50_000_000:
                        success_downscale = True
                        break
                except Exception:
                    continue
                    
            if not success_downscale:
                fallback_msg = f"⚠️ <b>Video too large for Telegram natively (>50MB).</b>\n🔗 <a href='{next_item['url']}'>Direct Media Link</a>\n\n{caption}"
                msg = await context.bot.send_message(chat_id=chat_id, text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
                review_dict[msg.message_id] = next_item
                unreviewed_count += 1
                save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "unreviewed_count"})
                await status_msg.delete()
                return True
                
        with open(temp_path, 'rb') as f:
            if next_item['type'] == 'photo':
                msg = await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            else:
                v_kwargs = {}
                if next_item.get('width'): v_kwargs['width'] = next_item['width']
                if next_item.get('height'): v_kwargs['height'] = next_item['height']
                msg = await context.bot.send_video(chat_id=chat_id, video=f, caption=caption, reply_markup=reply_markup, parse_mode="HTML", **v_kwargs)
            
        review_dict[msg.message_id] = next_item
        unreviewed_count += 1
        save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "unreviewed_count"})
        await status_msg.delete()
        return True
    except Exception as e:
        print(f"Error downloading/sending media: {e}")
        fallback_msg = f"⚠️ <b>Media download failed (Timeout/Error).</b>\n🔗 <a href='{next_item['url']}'>Direct Media Link</a>\n\n{caption}"
        msg = await status_msg.edit_text(text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
        review_dict[msg.message_id] = next_item
        unreviewed_count += 1
        save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "unreviewed_count"})
        return True
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                print(f"Failed to clean up temp file: {e}")

async def drip_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    if tweet_queue:
        await send_next_tweet(chat_id, context)
    else:
        await do_scrape(context, chat_id)
        if tweet_queue:
            await send_next_tweet(chat_id, context)

async def start_drip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not context.job_queue:
        await update.message.reply_text("Error: JobQueue is not initialized on this server.")
        return
        
    try:
        minutes = float(context.args[0])
        if minutes < 1:
            await update.message.reply_text("Please specify at least 1 minute.")
            return
            
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in current_jobs:
            job.schedule_removal()
            
        context.job_queue.run_repeating(drip_job, interval=minutes * 60, first=1, chat_id=chat_id, name=str(chat_id))
        await update.message.reply_text(f"💧 Drip feed activated! I will send you 1 video/photo every {minutes} minutes.\n\n⚠️ Note: Drip works best within active sessions. If the server sleeps, drip pauses until your next message wakes it up.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /drip <minutes>\nExample: /drip 10 (every 10 minutes)")

async def stop_drip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not context.job_queue:
        return
        
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if not current_jobs:
        await update.message.reply_text("No active drip feed.")
        return
    for job in current_jobs:
        job.schedule_removal()
    await update.message.reply_text("🛑 Drip feed stopped.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'channel':
        return

    await update.message.reply_text(
        "Welcome to the Twitter Curator Bot!\n\n"
        "Commands:\n"
        "/scrape - Force a manual scrape\n"
        "/next - Manually curate the queue\n"
        "/drip <minutes> - Auto-send media on a schedule\n"
        "/stopdrip - Stop auto-sending"
    )

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /channel <id>")
        return
    config['telegram_channel_id'] = context.args[0]
    os.environ['TELEGRAM_CHANNEL_ID'] = context.args[0]
    await update.message.reply_text(f"Channel ID saved as {config['telegram_channel_id']}")

is_filling = False


async def auto_scrape_job(context: ContextTypes.DEFAULT_TYPE):
    global tweet_queue, history, unreviewed_count, custom_list_url, bot_stats
    if len(tweet_queue) >= 30:
        return
    active_url = custom_list_url if custom_list_url else config['twitter_list_url']
    if not active_url:
        return
    list_id = active_url.rstrip('/').split('/')[-1]
    try:
        items = await extract_media_from_twitter(list_id)
        if not items:
            return
        history_set = set(history)
        queue_urls = {q.get('url') for q in tweet_queue}
        count = 0
        added_items = []
        for item in items:
            url = item['url']
            if url not in history_set and url not in queue_urls:
                added_items.append(item)
                history.append(url)
                history_set.add(url)
                count += 1
        if added_items:
            tweet_queue = added_items + tweet_queue
            if len(history) > 8000:
                history = history[-8000:]
            save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "history"})
            print(f"Auto-scrape completed: found {count} new items.")
    except Exception as e:
        print(f"Auto-scrape failed: {e}")
async def fill_buffer(chat_id, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count, is_filling
    
    # Don't auto-fill if a drip feed is actively running for this chat
    if context.job_queue:
        if context.job_queue.get_jobs_by_name(str(chat_id)):
            return
            
    if is_filling:
        return
    is_filling = True
    try:
        while unreviewed_count < 5 and tweet_queue:
            success = await send_next_tweet(chat_id, context)
            if not success:
                break
            await asyncio.sleep(1)  # ponytail: small delay prevents Telegram rate limits on free tier
    finally:
        is_filling = False

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asyncio.ensure_future(fill_buffer(update.message.chat_id, context))

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(VERSION)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tweet_queue, unreviewed_count, media_filter
    msg = f"📊 *Bot Status*\n\n"
    msg += f"📦 Queue: {len(tweet_queue)} items\n"
    msg += f"👀 Unreviewed Buffer: {unreviewed_count}\n"
    msg += f"🎛️ Active Filter: {media_filter}\n"
    msg += f"🤖 Version: {VERSION}"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def set_counter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count, tweet_queue, history
    if not context.args:
        await update.message.reply_text("Usage: /setcounter <number>\nExample: /setcounter 5")
        return
    try:
        new_count = int(context.args[0])
        if new_count < 0:
            new_count = 0
        unreviewed_count = new_count
        save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats)
        await update.message.reply_text(f"✅ Unreviewed counter manually set to {unreviewed_count}.")
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number.")


async def purgequeue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tweet_queue, unreviewed_count
    length = len(tweet_queue)
    tweet_queue.clear()
    unreviewed_count = 0
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "unreviewed_count"})
    await update.message.reply_text(f"🗑️ Queue purged! Deleted {length} pending items.")
async def filter_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global media_filter, tweet_queue, history, unreviewed_count
    media_filter = "photo"
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats)
    await update.message.reply_text("🖼️ Filter set: Photos only")

async def filter_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global media_filter, tweet_queue, history, unreviewed_count
    media_filter = "video"
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats)
    await update.message.reply_text("🎬 Filter set: Videos only")

async def filter_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global media_filter, tweet_queue, history, unreviewed_count
    media_filter = "all"
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats)
    await update.message.reply_text("📦 Filter set: All media")


async def setlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global custom_list_url
    if not context.args:
        await update.message.reply_text("Usage: /setlist <twitter_list_url>")
        return
    custom_list_url = context.args[0]
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"custom_list_url"})
    await update.message.reply_text(f"✅ List updated! Next scrape will use: {custom_list_url}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stats
    msg = f"📊 *Lifetime Curation Stats*\n\n"
    msg += f"❤️ Loved: {bot_stats.get('loved', 0)}\n"
    msg += f"🗑️ Skipped: {bot_stats.get('skipped', 0)}\n"
    msg += f"🔍 Total Reviewed: {bot_stats.get('loved', 0) + bot_stats.get('skipped', 0)}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")
async def setcookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global custom_cookies
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setcookies <auth_token> <ct0>")
        return
    custom_cookies['auth_token'] = context.args[0]
    custom_cookies['ct0'] = context.args[1]
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"custom_cookies"})
    await update.message.reply_text("✅ Twitter cookies updated successfully! You can run /scrape now.")

async def rt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global include_retweets
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Usage: /rt on or /rt off")
        return
    include_retweets = (context.args[0].lower() == 'on')
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"include_retweets"})
    state = "included" if include_retweets else "ignored"
    await update.message.reply_text(f"🔁 Retweets will now be {state} when scraping.")

async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_skipped, tweet_queue
    if not last_skipped:
        await update.message.reply_text("No recently skipped item found in memory.")
        return
    # Put it at the front of the queue
    tweet_queue.insert(0, last_skipped)
    last_skipped = None # Consume it
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue"})
    await update.message.reply_text("⏪ Undo successful! The skipped item has been placed back at the front of the queue.")
    # Trigger next automatically
    asyncio.ensure_future(fill_buffer(update.message.chat_id, context))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == "like":
        bot_stats["loved"] = bot_stats.get("loved", 0) + 1
        channel_id = config.get('telegram_channel_id')
        if not channel_id:
            await query.message.reply_text("Error: You haven't set a Channel ID yet! Use /channel <id>")
            return
            
        try:
            await context.bot.copy_message(
                chat_id=channel_id,
                from_chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            # Message may have already been deleted — still count it as reviewed
            print(f"Copy to channel failed: {e}")
        
        try:
            await query.message.delete()
        except Exception:
            pass
        review_dict.pop(query.message.message_id, None)
        unreviewed_count = max(0, unreviewed_count - 1)
        save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"bot_stats", "unreviewed_count"})
            
    elif action == "skip":
        bot_stats["skipped"] = bot_stats.get("skipped", 0) + 1
        global last_skipped
        item = review_dict.pop(query.message.message_id, None)
        if item:
            last_skipped = item
            
        try:
            await query.message.delete()
        except Exception:
            pass
        unreviewed_count = max(0, unreviewed_count - 1)
        save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"bot_stats", "unreviewed_count"})
        
    elif action == "pause":
        # Stop any active drip feeds
        if context.job_queue:
            current_jobs = context.job_queue.get_jobs_by_name(str(query.message.chat_id))
            for job in current_jobs:
                job.schedule_removal()
                
        # Remove the pause button from this message to show it's paused
        keyboard = [
            [
                InlineKeyboardButton("❤️ Love (Save to Channel)", callback_data="like"),
                InlineKeyboardButton("👎 Skip", callback_data="skip")
            ]
        ]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
                
        await context.bot.send_message(chat_id=query.message.chat_id, text="⏸️ Paused! (Auto-drip stopped). The video above is safely in your chat history—just Love/Skip it when you're ready to continue.")
        return

    # Automatically fill the buffer back up to 5 as a background task
    asyncio.ensure_future(fill_buffer(query.message.chat_id, context))

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = str(update.channel_post.chat.id)
    config['telegram_channel_id'] = channel_id
    os.environ['TELEGRAM_CHANNEL_ID'] = channel_id
    print(f"Auto-detected Channel ID: {channel_id}")

async def post_init(application: Application):
    application.job_queue.run_repeating(auto_scrape_job, interval=3600, first=60)
    await application.bot.set_my_commands([
        ("setlist", "Switch Twitter List URL"),
        ("purgequeue", "Delete everything in the queue"),
        ("stats", "View lifetime curation stats"),
        ("next", "Load the next item in the queue"),
        ("scrape", "Force a manual scrape for more media"),
        ("drip", "Auto-send media on a schedule (e.g. /drip 10)"),
        ("stopdrip", "Stop auto-sending"),
        ("clearhistory", "Wipe the scraper's memory so you can see old tweets again"),
        ("channel", "Set your private channel ID"),
        ("status", "Check queue length and unreviewed counter"),
        ("setcounter", "Manually fix counter drift (e.g. /setcounter 5)"),
        ("fv", "Filter: Videos only"),
        ("fp", "Filter: Photos only"),
        ("fa", "Filter: All media"),
        ("undo", "Undo your last skip"),
        ("setcookies", "Update Twitter cookies"),
        ("rt", "Toggle retweets (on/off)"),
        ("v", "Check current bot version"),
    ])

def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    app = ApplicationBuilder().token(config['telegram_bot_token']).read_timeout(60.0).write_timeout(60.0).connect_timeout(60.0).pool_timeout(60.0).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("purgequeue", purgequeue_command))
    app.add_handler(CommandHandler("setlist", setlist_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("scrape", scrape_tweets))
    app.add_handler(CommandHandler("clearhistory", clear_history))
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("v", version_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("setcounter", set_counter_command))
    app.add_handler(CommandHandler("fv", filter_video))
    app.add_handler(CommandHandler("fp", filter_photo))
    app.add_handler(CommandHandler("fa", filter_all))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("setcookies", setcookies_command))
    app.add_handler(CommandHandler("rt", rt_command))
    app.add_handler(CommandHandler("channel", set_channel))
    app.add_handler(CommandHandler("drip", start_drip))
    app.add_handler(CommandHandler("stopdrip", stop_drip))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))
    
    webhook_url = f"{RENDER_URL}/{config['telegram_bot_token']}"
    
    print(f"Starting webhook on port {PORT}...")
    print(f"Webhook URL: {webhook_url}")
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=config['telegram_bot_token'],
        webhook_url=webhook_url,
    )

if __name__ == '__main__':
    main()