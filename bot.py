import json
import os
import html
import asyncio
import re
import httpx
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apify_client import ApifyClient
import concurrent.futures

# Config from environment variables, falling back to config.json if present
config = {
    'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'telegram_channel_id': os.environ.get('TELEGRAM_CHANNEL_ID', ''),
    'twitter_list_url': os.environ.get('TWITTER_LIST_URL', ''),
    'apify_api_token': os.environ.get('APIFY_API_TOKEN', ''),
    'twitter_auth_token': os.environ.get('TWITTER_AUTH_TOKEN', ''),
    'twitter_ct0': os.environ.get('TWITTER_CT0', '')
}

if os.path.exists('config.json'):
    try:
        with open('config.json', 'r') as f:
            cfg_file = json.load(f)
            for k, v in cfg_file.items():
                if not config.get(k):
                    config[k] = v
    except Exception as e:
        print(f"Failed to load config.json fallback: {e}")

PORT = int(os.environ.get('PORT', 8000))
PUBLIC_URL = os.environ.get('PUBLIC_URL') or os.environ.get('KOYEB_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL', '')

apify_client = ApifyClient(config['apify_api_token'])

# Initialize persistent storage on Apify to survive Render sleep cycles
try:
    store = apify_client.key_value_stores().get_or_create(name='twitter-curation-bot-storage')
    store_client = apify_client.key_value_store(store.id)
except Exception as e:
    print(f"Failed to connect to Apify KV Store: {e}")
    store_client = None

_storage_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_active_background_tasks = set()

def _sync_set_records(records):
    import time
    for k, v in records.items():
        success = False
        for attempt in range(3):
            try:
                store_client.set_record(k, v)
                success = True
                break
            except Exception as e:
                time.sleep(0.5 * (2 ** attempt))
        if not success:
            print(f"Error: Failed to save {k} to KV store after 3 attempts.")

def load_data():
    tweet_queue = []
    history = []
    unreviewed_count = 0
    media_filter = "all"
    custom_cookies = {}
    include_retweets = True
    custom_list_url = ""
    bot_stats = {"loved": 0, "skipped": 0}
    list1_url = ""
    list2_url = ""
    active_list = "1"
    review_dict = {}
    
    if store_client:
        keys_to_fetch = [
            "queue", "history", "unreviewed_count", "media_filter",
            "custom_cookies", "include_retweets", "list1_url", "custom_list_url",
            "list2_url", "active_list", "bot_stats", "review_dict"
        ]
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_key = {executor.submit(store_client.get_record, k): k for k in keys_to_fetch}
            for future in concurrent.futures.as_completed(future_to_key):
                k = future_to_key[future]
                try:
                    results[k] = future.result()
                except Exception as e:
                    print(f"Error loading {k} from KV store: {e}")
                    results[k] = None

        q_rec = results.get("queue")
        if q_rec and q_rec.get('value'):
            raw_queue = q_rec['value']
            seen_tweets = {}
            coalesced = []
            for it in raw_queue:
                if it.get('tweet_url') and '/unknown/' in it['tweet_url']:
                    it['tweet_url'] = it['tweet_url'].replace('/unknown/', '/i/')
                t_url = it.get('tweet_url')
                if it.get('type') in ['photo', 'album'] and t_url:
                    if t_url in seen_tweets:
                        ex = seen_tweets[t_url]
                        ex['type'] = 'album'
                        e_urls = ex.setdefault('urls', [ex['url']])
                        for x in it.get('urls', [it.get('url')]):
                            if x and x not in e_urls:
                                e_urls.append(x)
                    else:
                        cloned = dict(it)
                        if cloned.get('text'):
                            cloned['text'] = re.sub(r'\s*https://t\.co/[a-zA-Z0-9]+$', '', cloned['text']).strip()
                        seen_tweets[t_url] = cloned
                        coalesced.append(cloned)
                else:
                    coalesced.append(it)
            tweet_queue = coalesced

        h_rec = results.get("history")
        if h_rec and h_rec.get('value'):
            history = h_rec['value']
            if len(history) > 5000:
                history = history[-5000:]

        u_rec = results.get("unreviewed_count")
        if u_rec and u_rec.get('value') is not None:
            unreviewed_count = u_rec['value']

        f_rec = results.get("media_filter")
        if f_rec and f_rec.get('value'):
            media_filter = f_rec['value']

        c_rec = results.get("custom_cookies")
        if c_rec and c_rec.get('value'):
            custom_cookies = c_rec['value']

        r_rec = results.get("include_retweets")
        if r_rec and r_rec.get('value') is not None:
            include_retweets = r_rec['value']

        l1_rec = results.get("list1_url")
        if l1_rec and l1_rec.get('value'):
            list1_url = l1_rec['value']
        else:
            cl_rec = results.get("custom_list_url")
            if cl_rec and cl_rec.get('value'):
                list1_url = cl_rec['value']

        l2_rec = results.get("list2_url")
        if l2_rec and l2_rec.get('value'):
            list2_url = l2_rec['value']

        act_rec = results.get("active_list")
        if act_rec and act_rec.get('value'):
            active_list = str(act_rec['value'])

        s_rec = results.get("bot_stats")
        if s_rec and s_rec.get('value'):
            bot_stats = s_rec['value']

        rd_rec = results.get("review_dict")
        if rd_rec and rd_rec.get('value'):
            review_dict = {str(k): v for k, v in rd_rec['value'].items()}
            for k, it in review_dict.items():
                if isinstance(it, dict) and it.get('tweet_url') and '/unknown/' in it['tweet_url']:
                    it['tweet_url'] = it['tweet_url'].replace('/unknown/', '/i/')

    if not list1_url:
        list1_url = config['twitter_list_url']
    custom_list_url = list2_url if (active_list == "2" and list2_url) else list1_url
            
    return tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, list1_url, list2_url, active_list, review_dict

tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, list1_url, list2_url, active_list, review_dict = load_data()

def get_active_list_url():
    if active_list == "2" and list2_url:
        return list2_url
    return list1_url or config['twitter_list_url']

def save_lists():
    if store_client:
        curr_url = get_active_list_url()
        records = {
            "custom_list_url": curr_url,
            "list1_url": list1_url,
            "list2_url": list2_url,
            "active_list": active_list,
        }
        _storage_executor.submit(_sync_set_records, records)

def save_data(tweet_queue=None, history=None, unreviewed_count=None, media_filter=None, custom_cookies=None, include_retweets=None, custom_list_url=None, bot_stats=None, review_dict=None, keys=None):
    if not store_client:
        return
    if keys is None:
        keys = {"queue", "history", "unreviewed_count", "media_filter", "custom_cookies", "include_retweets", "custom_list_url", "bot_stats", "review_dict"}
    records = {}
    if "queue" in keys:
        val = tweet_queue if tweet_queue is not None else globals().get('tweet_queue', [])
        records["queue"] = list(val)
    if "history" in keys:
        val = history if history is not None else globals().get('history', [])
        if len(val) > 5000:
            val = val[-5000:]
            globals()['history'] = val
        records["history"] = list(val)
    if "unreviewed_count" in keys:
        records["unreviewed_count"] = unreviewed_count if unreviewed_count is not None else globals().get('unreviewed_count', 0)
    if "media_filter" in keys:
        records["media_filter"] = media_filter if media_filter is not None else globals().get('media_filter', 'all')
    if "custom_cookies" in keys:
        records["custom_cookies"] = dict(custom_cookies if custom_cookies is not None else globals().get('custom_cookies', {}))
    if "include_retweets" in keys:
        records["include_retweets"] = include_retweets if include_retweets is not None else globals().get('include_retweets', False)
    if "custom_list_url" in keys or "lists" in keys:
        records["custom_list_url"] = get_active_list_url()
        records["list1_url"] = globals().get('list1_url', '')
        records["list2_url"] = globals().get('list2_url', '')
        records["active_list"] = globals().get('active_list', '1')
    if "bot_stats" in keys:
        records["bot_stats"] = dict(bot_stats if bot_stats is not None else globals().get('bot_stats', {}))
    if "review_dict" in keys:
        records["review_dict"] = dict(review_dict if review_dict is not None else globals().get('review_dict', {}))

    _storage_executor.submit(_sync_set_records, records)

last_skipped = None

def extract_media_from_tweet_node(tweet_node):
    media_list = []
    if not tweet_node or not isinstance(tweet_node, dict):
        return media_list
    legacy_node = tweet_node.get('legacy', {})
    std_media = (
        legacy_node.get('extended_entities', {}).get('media', []) or
        tweet_node.get('extended_entities', {}).get('media', []) or
        legacy_node.get('entities', {}).get('media', [])
    )
    if std_media:
        media_list.extend(std_media)
        
    card = tweet_node.get('card', {})
    for b in card.get('legacy', {}).get('binding_values', []):
        if b.get('key') == 'unified_card':
            try:
                val = json.loads(b['value']['string_value'])
                media_entities = val.get('media_entities', {})
                for me in media_entities.values():
                    media_list.append(me)
            except Exception:
                pass
    return media_list

async def extract_media_from_twitter(list_id, target_count=None, known_urls=None):
    extracted_items = []
    new_items_found = 0
    
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
                raise Exception(f"Twitter API error (HTTP {res.status_code}): {err_text}")
                
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
                            tweet = result.get('tweet', result)
                            legacy = tweet.get('legacy', {})
                            user_res = tweet.get('core', {}).get('user_results', {}).get('result', {})
                            u_core = user_res.get('core', {})
                            u_legacy = user_res.get('legacy', {})
                            screen_name = u_core.get('screen_name') or u_legacy.get('screen_name') or 'unknown'
                            tweet_id = legacy.get('id_str') or tweet.get('rest_id', '')
                            if screen_name and screen_name != 'unknown':
                                tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
                            else:
                                tweet_url = f"https://x.com/i/status/{tweet_id}"
                            tweet_text = legacy.get('full_text', '')
                            
                            # Check if retweet
                            rt_data = tweet.get('retweeted_status_result') or legacy.get('retweeted_status_result')
                            target_tweet = tweet
                            if rt_data:
                                if not include_retweets:
                                    continue # Skip retweets when /rt off is set
                                rt_res = rt_data.get('result', {})
                                rt_target = rt_res.get('tweet', rt_res)
                                rt_user_res = rt_target.get('core', {}).get('user_results', {}).get('result', {})
                                rt_screen_name = rt_user_res.get('core', {}).get('screen_name') or rt_user_res.get('legacy', {}).get('screen_name')
                                if rt_screen_name:
                                    screen_name = rt_screen_name
                                    tweet_id = rt_target.get('legacy', {}).get('id_str') or rt_target.get('rest_id', '')
                                    tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
                                    tweet_text = rt_target.get('legacy', {}).get('full_text', tweet_text)
                                target_tweet = rt_target
                                
                            # Clean trailing t.co attachment links
                            tweet_text = re.sub(r'\s*https://t\.co/[a-zA-Z0-9]+$', '', tweet_text).strip()
                                
                            media = extract_media_from_tweet_node(target_tweet)
                            
                            photos = [m for m in media if m.get('type') == 'photo']
                            videos = [m for m in media if m.get('type') in ['video', 'animated_gif'] or m.get('video_info')]
                            
                            if len(photos) > 1:
                                photo_urls = [m.get('media_url_https') or m.get('media_url') for m in photos if m.get('media_url_https') or m.get('media_url')]
                                if photo_urls:
                                    album_obj = {
                                        'tweet_url': tweet_url,
                                        'text': tweet_text,
                                        'screen_name': screen_name,
                                        'type': 'album',
                                        'urls': photo_urls,
                                        'url': photo_urls[0],
                                    }
                                    orig = photos[0].get('original_info', {})
                                    if orig.get('width') and orig.get('height'):
                                        album_obj['width'] = orig['width']
                                        album_obj['height'] = orig['height']
                                    extracted_items.append(album_obj)
                                    if known_urls is None or any(u not in known_urls for u in photo_urls):
                                        new_items_found += 1
                            elif len(photos) == 1:
                                m = photos[0]
                                p_url = m.get('media_url_https') or m.get('media_url')
                                if p_url:
                                    media_obj = {
                                        'tweet_url': tweet_url,
                                        'text': tweet_text,
                                        'screen_name': screen_name,
                                        'type': 'photo',
                                        'url': p_url,
                                        'urls': [p_url],
                                    }
                                    orig = m.get('original_info', {})
                                    if orig.get('width') and orig.get('height'):
                                        media_obj['width'] = orig['width']
                                        media_obj['height'] = orig['height']
                                    extracted_items.append(media_obj)
                                    if known_urls is None or p_url not in known_urls:
                                        new_items_found += 1
                                
                            for m in videos:
                                media_obj = {'tweet_url': tweet_url, 'text': tweet_text, 'screen_name': screen_name}
                                original_info = m.get('original_info', {})
                                if original_info.get('width') and original_info.get('height'):
                                    media_obj['width'] = original_info['width']
                                    media_obj['height'] = original_info['height']
                                    
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
                                    v_urls = media_obj.get('urls', [media_obj['url']])
                                    if known_urls is None or not any(vu in known_urls for vu in v_urls):
                                        new_items_found += 1
                                        
            # If we didn't get a new cursor, or we have found enough brand-new items, stop paginating early
            if not new_cursor:
                break
            if target_count and new_items_found >= target_count:
                break
            if not target_count and len(extracted_items) >= 500:
                break
            cursor = new_cursor
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"Error making GraphQL request: {e}")
            if "cookies" in str(e).lower() or "expired" in str(e).lower():
                raise e
            # Break immediately on network / API errors to avoid compounding 10x timeouts (Finding 2)
            break
                
    return extracted_items

_scrape_lock = None

def get_scrape_lock():
    global _scrape_lock
    if _scrape_lock is None:
        _scrape_lock = asyncio.Lock()
    return _scrape_lock

async def do_scrape(context: ContextTypes.DEFAULT_TYPE, chat_id: int, target_count: int = None):
    global tweet_queue, history, unreviewed_count
    lock = get_scrape_lock()
    was_locked = lock.locked()
    if was_locked:
        try:
            await context.bot.send_message(chat_id=chat_id, text="⏳ A scrape is already running in the background. Waiting for it to finish...")
        except Exception:
            pass

    async with lock:
        # If lock was already held and the queue now has items, return immediately without re-scraping (Finding 5)
        if was_locked and target_count and len(tweet_queue) >= target_count:
            return

        await context.bot.send_message(chat_id=chat_id, text=f"🔄 Scraping Twitter List {active_list}...")
        
        try:
            active_ct0 = custom_cookies.get('ct0') or config['twitter_ct0']
            active_auth_token = custom_cookies.get('auth_token') or config['twitter_auth_token']
            if not active_auth_token or not active_ct0:
                await context.bot.send_message(chat_id=chat_id, text="Error: Missing Twitter cookies! Use /setcookies <auth_token> <ct0>")
                return
                
            # Extract numeric list ID from active list URL
            active_url = get_active_list_url()
            if not active_url:
                await context.bot.send_message(chat_id=chat_id, text=f"Error: No Twitter list URL configured for List {active_list}! Set it with /list{active_list} <url>")
                return
                
            list_id = active_url.split('?')[0].split('#')[0].rstrip('/').split('/')[-1]
            history_set = set(history)
            queue_urls = {q.get('url') for q in tweet_queue}
            known_urls = history_set | queue_urls
            items = await extract_media_from_twitter(list_id, target_count=target_count, known_urls=known_urls)
            
            count = 0
            added_items = []
            
            # Optimize O(N^2) list scan to O(1) lookups
            history_set = set(history)
            queue_urls = {q.get('url') for q in tweet_queue}
            
            for item in items:
                item['source_list'] = f"List {active_list}"
                item['source_list_num'] = active_list
                item_urls = item.get('urls', [item.get('url')])
                if any(u not in history_set for u in item_urls) and item['url'] not in queue_urls:
                    added_items.append(item)
                    for u in item_urls:
                        history.append(u)
                        history_set.add(u)
                    count += 1
                    
            # Prepend new items so the freshest media is served first
            tweet_queue = added_items + tweet_queue
            
            # Prevent history from growing infinitely and crashing memory
            if len(history) > 8000:
                history = history[-8000:]
            
            save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "history"})
            await context.bot.send_message(chat_id=chat_id, text=f"✅ Scraped {len(items)} posts from List {active_list}, found {count} brand new ones! Total in queue: {len(tweet_queue)}")
        except Exception as e:
            if "cookies" in str(e).lower() or "expired" in str(e).lower():
                await context.bot.send_message(chat_id=chat_id, text=f"{e}")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Error scraping: {e}")

async def scrape_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_scrape(context, update.message.chat_id, target_count=50)
    if tweet_queue:
        await send_next_tweet(update.message.chat_id, context)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count
    history.clear()
    unreviewed_count = 0
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"history", "unreviewed_count"})
    await update.message.reply_text("🗑️ History cleared! The scraper will now re-fetch older tweets as if they were brand new.")

# Reuse TCP connections
_http_client = None

def get_http_client():
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=180.0)
    return _http_client

# Dead gofile / temp helpers pruned for ponytail simplicity

VERSION = "v1.22.0"

async def send_next_tweet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    global tweet_queue, history, unreviewed_count, bot_stats
    if not tweet_queue:
        await do_scrape(context, chat_id, target_count=30)
        if not tweet_queue:
            await context.bot.send_message(chat_id=chat_id, text="Still empty! Try scraping again later when the Twitter list has new posts.")
            return False
    
    match_index = -1
    for i, item in enumerate(tweet_queue):
        if media_filter == "all":
            match_index = i
            break
        elif media_filter == "video" and item.get('type') == 'video':
            match_index = i
            break
        elif media_filter == "photo" and item.get('type') in ['photo', 'album']:
            match_index = i
            break
            
    if match_index == -1:
        f_type = "videos" if media_filter == "video" else "photos"
        await context.bot.send_message(chat_id=chat_id, text=f"No {f_type} left in the queue! They might have been filtered out. Try changing the filter with /fa or run /scrape.")
        return False

    # Do not pop from tweet_queue yet - ensure delivery succeeds first (Finding 10)
    raw_item = tweet_queue[match_index]
    next_item = dict(raw_item)
    
    # Merge any sibling photos for this tweet still in tweet_queue
    if next_item.get('type') in ['photo', 'album'] and next_item.get('tweet_url'):
        same_items = [it for it in tweet_queue if it.get('tweet_url') == next_item['tweet_url'] and it.get('type') in ['photo', 'album']]
        if len(same_items) > 1 or next_item.get('type') == 'album':
            next_item['type'] = 'album'
            urls = next_item.setdefault('urls', [next_item['url']])
            for it in same_items:
                it_urls = it.get('urls', [it.get('url')])
                for u in it_urls:
                    if u and u not in urls:
                        urls.append(u)
                        
    # Strip trailing t.co attachment links from caption if present
    if next_item.get('text'):
        next_item['text'] = re.sub(r'\s*https://t\.co/[a-zA-Z0-9]+$', '', next_item['text']).strip()

    tweet_x_url = next_item.get('tweet_url', '')
    if '/unknown/' in tweet_x_url:
        tweet_x_url = tweet_x_url.replace('/unknown/', '/i/')
    if not tweet_x_url or 'status/' not in tweet_x_url:
        tweet_x_url = f"https://x.com/i/status/{next_item.get('id', '')}"
    tweet_x_url = tweet_x_url.replace('vxtwitter.com', 'x.com')
    if not tweet_x_url.startswith('http'):
        tweet_x_url = f"https://x.com/i/status/{next_item.get('id', '')}"

    row2 = [InlineKeyboardButton("⏸️ Pause", callback_data="pause")]
    if tweet_x_url and tweet_x_url.startswith("http"):
        row2.append(InlineKeyboardButton("🔗 View on X", url=tweet_x_url))

    keyboard = [
        [
            InlineKeyboardButton("❤️ Save", callback_data="like"),
            InlineKeyboardButton("👎 Skip", callback_data="skip")
        ],
        row2
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

    badge_parts.append(f"📦 {len(tweet_queue)} left")
        
    badge_header = f"<b>{' • '.join(badge_parts)}</b>\n\n" if badge_parts else ""
    
    # Creator username directly on link
    author = next_item.get('screen_name')
    if not author or author in ('unknown', 'i'):
        parts = next_item.get('tweet_url', '').split('/')
        if len(parts) >= 4 and parts[3] not in ('', 'unknown', 'i'):
            author = parts[3]
    author_label = f"@{author}" if author and author not in ('unknown', 'i') else "Link to Tweet"

    safe_text = html.escape(next_item['text'][:800])
    src_num = next_item.get('source_list_num')
    list_label = f" • <i>List {src_num}</i>" if src_num else ""
    caption = f"{badge_header}{safe_text}\n\n<a href='{next_item['tweet_url']}'>{author_label}</a>{list_label}\n\n<code>{VERSION}</code>"
    
    # Direct delivery without 'Loading next item...' placeholder (Finding 6)
    delivered_msg_id = None

    if next_item.get('type') == 'album':
        photo_urls = next_item.get('urls', [next_item['url']])
        try:
            input_media = []
            for idx, p_url in enumerate(photo_urls):
                if idx == 0:
                    input_media.append(InputMediaPhoto(media=p_url, caption=caption, parse_mode="HTML"))
                else:
                    input_media.append(InputMediaPhoto(media=p_url))
            
            media_msgs = await context.bot.send_media_group(chat_id=chat_id, media=input_media)
            next_item['album_message_ids'] = [m.message_id for m in media_msgs]
            
            control_text = f"📸 <b>Album ({len(photo_urls)} photos)</b> • Choose action:"
            ctrl_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=control_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                reply_to_message_id=media_msgs[0].message_id
            )
            delivered_msg_id = ctrl_msg.message_id
        except Exception as e:
            print(f"Error sending album via URL: {e}")
            fallback_msg = f"⚠️ <b>Album sending failed ({e}).</b>\n🔗 <a href='{next_item.get('tweet_url', '')}'>View on X</a>\n\n{caption}"
            ctrl_msg = await context.bot.send_message(chat_id=chat_id, text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
            delivered_msg_id = ctrl_msg.message_id

    elif next_item.get('type') == 'photo':
        msg = None
        try:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=next_item['url'],
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Direct photo send by URL failed: {e}")
            tf_path = None
            try:
                client = get_http_client()
                async with client.stream("GET", next_item['url'], follow_redirects=True, timeout=20.0) as resp:
                    if resp.status_code == 200:
                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                            tf_path = tf.name
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                tf.write(chunk)
                        with open(tf_path, "rb") as photo_fp:
                            msg = await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo_fp,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode="HTML"
                            )
            except Exception as dl_err:
                print(f"Photo upload fallback failed: {dl_err}")
            finally:
                if tf_path and os.path.exists(tf_path):
                    try:
                        os.remove(tf_path)
                    except Exception:
                        pass

        if not msg:
            fallback_msg = f"⚠️ <b>Photo display failed.</b>\n🔗 <a href='{next_item.get('tweet_url', '')}'>View on X</a> • <a href='{next_item['url']}'>Direct Photo Link</a>\n\n{caption}"
            msg = await context.bot.send_message(chat_id=chat_id, text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
        delivered_msg_id = msg.message_id

    elif next_item.get('type') == 'video':
        urls_to_try = next_item.get('urls', [next_item['url']])
        msg = None
        v_kwargs = {}
        if next_item.get('width'): v_kwargs['width'] = next_item['width']
        if next_item.get('height'): v_kwargs['height'] = next_item['height']
        if next_item.get('duration_millis'): v_kwargs['duration'] = round(next_item['duration_millis'] / 1000)
        
        # 1. First attempt: Zero-bandwidth direct URL passthrough
        for u in urls_to_try:
            try:
                msg = await context.bot.send_video(
                    chat_id=chat_id,
                    video=u,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    **v_kwargs
                )
                break
            except Exception as e:
                print(f"Direct video URL send failed for {u}: {e}")
                continue
                
        # 2. Second attempt: If URL send failed, stream-download and upload directly (20s timeout, up to 50MB)
        if not msg:
            client = get_http_client()
            for u in urls_to_try:
                tf_path = None
                try:
                    async with client.stream("GET", u, follow_redirects=True, timeout=20.0) as stream_resp:
                        if stream_resp.status_code == 200:
                            cl_header = stream_resp.headers.get("content-length")
                            if cl_header and int(cl_header) > 50 * 1024 * 1024:
                                continue
                            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                                tf_path = tf.name
                                total_bytes = 0
                                too_large = False
                                async for chunk in stream_resp.aiter_bytes(chunk_size=131072):
                                    total_bytes += len(chunk)
                                    if total_bytes > 50 * 1024 * 1024:
                                        too_large = True
                                        break
                                    tf.write(chunk)
                            if too_large:
                                continue
                            with open(tf_path, "rb") as video_fp:
                                msg = await context.bot.send_video(
                                    chat_id=chat_id,
                                    video=video_fp,
                                    caption=caption,
                                    reply_markup=reply_markup,
                                    parse_mode="HTML",
                                    **v_kwargs
                                )
                            break
                except Exception as dl_err:
                    print(f"Direct stream download & upload fallback failed for {u}: {dl_err}")
                finally:
                    if tf_path and os.path.exists(tf_path):
                        try:
                            os.remove(tf_path)
                        except Exception:
                            pass

        if not msg:
            t_url = next_item.get('tweet_url', '')
            if '/unknown/' in t_url:
                t_url = t_url.replace('/unknown/', '/i/')
            if not t_url or 'status/' not in t_url:
                t_url = f"https://x.com/i/status/{next_item.get('id', '')}"
            watch_x_url = t_url.replace('vxtwitter.com', 'x.com')
            fxtwitter_url = t_url.replace('vxtwitter.com', 'fxtwitter.com').replace('x.com', 'fxtwitter.com')
            media_url = next_item.get('url', '')
            fallback_msg = (
                f"⚠️ <b>Video exceeds Telegram's 50MB upload limit.</b>\n\n"
                f"🔗 <a href='{watch_x_url}'>Watch on X</a> • "
                f"<a href='{fxtwitter_url}'>Web Player (FxTwitter)</a> • "
                f"<a href='{media_url}'>Direct MP4</a>\n\n"
                f"{caption}"
            )
            msg = await context.bot.send_message(chat_id=chat_id, text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
        delivered_msg_id = msg.message_id

    # Delivery confirmed! Remove from tweet_queue now (Finding 10)
    if next_item.get('type') in ['photo', 'album'] and next_item.get('tweet_url'):
        tweet_queue = [it for it in tweet_queue if not (it.get('tweet_url') == next_item['tweet_url'] and it.get('type') in ['photo', 'album'])]
    else:
        if match_index < len(tweet_queue) and tweet_queue[match_index].get('url') == next_item.get('url'):
            tweet_queue.pop(match_index)
        else:
            tweet_queue = [it for it in tweet_queue if it.get('url') != next_item.get('url')]

    review_dict[str(delivered_msg_id)] = next_item
    unreviewed_count += 1
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, review_dict, keys={"queue", "unreviewed_count", "review_dict"})
    return True
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
        "/lists - View & switch between your 2 Twitter lists\n"
        "/list1 [url] - Switch to or set List 1\n"
        "/list2 [url] - Switch to or set List 2\n"
        "/switchlist - Quick toggle between List 1 & List 2\n"
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
    global tweet_queue, history, unreviewed_count, bot_stats
    if len(tweet_queue) >= 30:
        return
    active_url = get_active_list_url()
    if not active_url:
        return
    list_id = active_url.split('?')[0].split('#')[0].rstrip('/').split('/')[-1]
    history_set = set(history)
    queue_urls = {q.get('url') for q in tweet_queue}
    known_urls = history_set | queue_urls
    try:
        items = await extract_media_from_twitter(list_id, target_count=30, known_urls=known_urls)
        if not items:
            return
        history_set = set(history)
        queue_urls = {q.get('url') for q in tweet_queue}
        count = 0
        added_items = []
        for item in items:
            item['source_list'] = f"List {active_list}"
            item['source_list_num'] = active_list
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
            print(f"Auto-scrape completed: found {count} new items from List {active_list}.")
    except Exception as e:
        print(f"Auto-scrape failed: {e}")
async def fill_buffer(chat_id, context: ContextTypes.DEFAULT_TYPE, notify_if_empty=False):
    global unreviewed_count, is_filling
    
    # Don't auto-fill if a drip feed is actively running for this chat (unless manually requested via /next)
    if not notify_if_empty and context.job_queue:
        if context.job_queue.get_jobs_by_name(str(chat_id)):
            return
            
    if is_filling:
        if notify_if_empty:
            await context.bot.send_message(chat_id=chat_id, text="⏳ Already preparing your next posts, one moment...")
        return

    if not tweet_queue:
        await do_scrape(context, chat_id, target_count=30)
        if not tweet_queue:
            if notify_if_empty:
                await context.bot.send_message(chat_id=chat_id, text=f"⚠️ The queue is empty! Run /scrape to fetch fresh posts from List {active_list}.")
            return

    if unreviewed_count >= 5:
        if notify_if_empty:
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ You already have {unreviewed_count} unreviewed posts waiting in chat! Review or skip them first, or use /setcounter 0 to reset.")
        return

    is_filling = True
    try:
        while unreviewed_count < 5 and tweet_queue:
            success = await send_next_tweet(chat_id, context)
            if not success:
                break
            await asyncio.sleep(0.1)
    finally:
        is_filling = False

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else update.message.chat_id
    try:
        await fill_buffer(chat_id, context, notify_if_empty=True)
    except Exception as e:
        print(f"Error in next_command: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error serving next item: {e}")

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(VERSION)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tweet_queue, unreviewed_count, media_filter, active_list
    msg = f"📊 *Bot Status*\n\n"
    msg += f"📦 Queue: {len(tweet_queue)} items\n"
    msg += f"👀 Unreviewed Buffer: {unreviewed_count}\n"
    msg += f"🎛️ Active Filter: {media_filter}\n"
    msg += f"📋 Active List: List {active_list} ({get_active_list_url()})\n"
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
    global tweet_queue, unreviewed_count, history
    purged_urls = set()
    for item in tweet_queue:
        if item.get('url'):
            purged_urls.add(item['url'])
        if item.get('urls'):
            for u in item['urls']:
                purged_urls.add(u)
        if item.get('tweet_url'):
            purged_urls.add(item['tweet_url'])

    if purged_urls:
        history = [h for h in history if h not in purged_urls]

    length = len(tweet_queue)
    tweet_queue.clear()
    unreviewed_count = 0
    save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, keys={"queue", "history", "unreviewed_count"})
    await update.message.reply_text(f"🗑️ Queue purged! Deleted {length} pending items and freed them to be re-scraped.")
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


async def lists_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global list1_url, list2_url, active_list
    l1_disp = list1_url if list1_url else "Not configured"
    l2_disp = list2_url if list2_url else "Not configured (set with /list2 <url>)"
    
    msg = "📋 <b>Twitter Lists</b>\n\n"
    msg += f"1️⃣ <b>List 1:</b> {l1_disp} {'<b>[ACTIVE ✅]</b>' if active_list == '1' else ''}\n\n"
    msg += f"2️⃣ <b>List 2:</b> {l2_disp} {'<b>[ACTIVE ✅]</b>' if active_list == '2' else ''}\n\n"
    msg += f"Current scraping source: <b>List {active_list}</b>\n\n"
    msg += "<i>Commands:</i>\n"
    msg += "• <code>/list1 [url]</code>\n"
    msg += "• <code>/list2 [url]</code>\n"
    msg += "• <code>/switchlist</code> (toggle)"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ List 1" if active_list == "1" else "▶️ Switch to List 1", callback_data="switch_list:1"),
            InlineKeyboardButton("✅ List 2" if active_list == "2" else "▶️ Switch to List 2", callback_data="switch_list:2"),
        ],
        [
            InlineKeyboardButton("🔄 Scrape Active List", callback_data="scrape_active")
        ]
    ]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def list1_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global list1_url, active_list, custom_list_url
    if context.args:
        list1_url = context.args[0]
        active_list = "1"
        save_lists()
        custom_list_url = get_active_list_url()
        await update.message.reply_text(f"✅ <b>List 1</b> updated and set as ACTIVE!\n🔗 {list1_url}", parse_mode="HTML")
    else:
        active_list = "1"
        save_lists()
        custom_list_url = get_active_list_url()
        await update.message.reply_text(f"✅ Switched to <b>List 1</b> (ACTIVE)\n🔗 {list1_url or 'None'}", parse_mode="HTML")

async def list2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global list2_url, active_list, custom_list_url
    if context.args:
        list2_url = context.args[0]
        active_list = "2"
        save_lists()
        custom_list_url = get_active_list_url()
        await update.message.reply_text(f"✅ <b>List 2</b> updated and set as ACTIVE!\n🔗 {list2_url}", parse_mode="HTML")
    else:
        if not list2_url:
            await update.message.reply_text("⚠️ List 2 URL is not set yet! Use:\n<code>/list2 &lt;twitter_list_url&gt;</code> to set it.", parse_mode="HTML")
            return
        active_list = "2"
        save_lists()
        custom_list_url = get_active_list_url()
        await update.message.reply_text(f"✅ Switched to <b>List 2</b> (ACTIVE)\n🔗 {list2_url}", parse_mode="HTML")

async def switchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_list, list1_url, list2_url, custom_list_url
    if active_list == "1":
        if not list2_url:
            await update.message.reply_text("⚠️ Cannot switch to List 2 because it isn't set yet! Set it with:\n<code>/list2 &lt;twitter_list_url&gt;</code>", parse_mode="HTML")
            return
        active_list = "2"
    else:
        active_list = "1"
    save_lists()
    custom_list_url = get_active_list_url()
    await update.message.reply_text(f"🔀 Switched active source to <b>List {active_list}</b>\n🔗 {custom_list_url}", parse_mode="HTML")

async def setlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global custom_list_url, list1_url, list2_url, active_list
    if not context.args:
        await update.message.reply_text("Usage:\n/setlist <twitter_list_url> (updates active list)\n/setlist 1 <url> (updates List 1)\n/setlist 2 <url> (updates List 2)")
        return
    
    if len(context.args) >= 2 and context.args[0] in ("1", "2"):
        target_num = context.args[0]
        url = context.args[1]
        if target_num == "1":
            list1_url = url
            active_list = "1"
        else:
            list2_url = url
            active_list = "2"
    else:
        url = context.args[0]
        if active_list == "2":
            list2_url = url
        else:
            list1_url = url
            
    custom_list_url = get_active_list_url()
    save_lists()
    await update.message.reply_text(f"✅ List {active_list} updated! Next scrape will use:\n{custom_list_url}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stats, tweet_queue
    loved = bot_stats.get('loved', 0)
    skipped = bot_stats.get('skipped', 0)
    total = loved + skipped
    rate = (loved / total * 100) if total > 0 else 0.0
    msg = f"📊 *Lifetime Curation Stats*\n\n"
    msg += f"❤️ Loved: {loved}\n"
    msg += f"🗑️ Skipped: {skipped}\n"
    msg += f"🔍 Total Reviewed: {total}\n"
    msg += f"✨ Love Rate: {rate:.1f}%\n"
    msg += f"📦 Queue Remaining: {len(tweet_queue)}\n"
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

async def cleanup_reviewed_message(query, action):
    deleted = False
    try:
        await query.message.delete()
        deleted = True
    except Exception as e:
        print(f"Delete message failed (likely >48h old): {e}")

    if not deleted:
        # Telegram API strictly forbids bots from deleting messages >48 hours old in private chats.
        # Fall back to stripping the interactive buttons so it cannot be clicked again,
        # and prepend a clear status badge to the caption.
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            print(f"Failed to strip reply markup on old message: {e}")

        try:
            tag = "❤️ <b>[SAVED TO CHANNEL]</b>" if action == "like" else "🗑️ <b>[SKIPPED]</b>"
            orig_caption = query.message.caption_html or query.message.text_html or ""
            new_caption = f"{tag}\n\n{orig_caption}"[:1024]
            if query.message.caption:
                await query.message.edit_caption(caption=new_caption, parse_mode="HTML")
            elif query.message.text:
                await query.message.edit_text(text=new_caption, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to edit caption on old message: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count, custom_list_url, active_list, bot_stats, last_skipped, tweet_queue, history, media_filter, custom_cookies, include_retweets, list1_url, list2_url, review_dict
    query = update.callback_query
    action = query.data
    chat_id = update.effective_chat.id if update.effective_chat else query.message.chat_id
    
    # 1. Answer callback toast once (Finding 9)
    if action == "like":
        await query.answer("❤️ Saved to channel!")
    elif action == "skip":
        await query.answer("🗑️ Skipped")
    elif not action.startswith("switch_list:"):
        await query.answer()
    
    try:
        msg_id_str = str(query.message.message_id)
        msg_id_int = query.message.message_id
        msg_text = query.message.text or query.message.caption or ""
        
        # Look up item in review_dict (supports both string and integer keys)
        item = review_dict.get(msg_id_str) or review_dict.get(msg_id_int)
        
        # Detect album control message even if memory was wiped during a sleep cycle
        is_album_control = ("Album (" in msg_text and "Choose action:" in msg_text) or (item and item.get('type') == 'album')
        
        album_mids = []
        if is_album_control:
            if item and item.get('album_message_ids'):
                album_mids = item['album_message_ids']
            elif query.message.reply_to_message:
                start_mid = query.message.reply_to_message.message_id
                album_mids = list(range(start_mid, msg_id_int))
            else:
                match = re.search(r'Album\s*\((\d+)\s*photos\)', msg_text)
                num_photos = int(match.group(1)) if match else 2
                album_mids = [msg_id_int - i for i in range(num_photos, 0, -1)]

        if action == "like":
            bot_stats["loved"] = bot_stats.get("loved", 0) + 1
            channel_id = config.get('telegram_channel_id')
            if not channel_id:
                await query.message.reply_text("Error: You haven't set a Channel ID yet! Use /channel <id>")
                return
                
            # Immediately strip buttons to prevent duplicate taps while background copy executes (Finding 1)
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
                
            # Background task for channel copying & chat cleanup (Findings 2, 3 & 8)
            async def _do_like_transfer():
                copy_success = False
                try:
                    if is_album_control:
                        if album_mids:
                            try:
                                await context.bot.copy_messages(
                                    chat_id=channel_id,
                                    from_chat_id=chat_id,
                                    message_ids=album_mids
                                )
                                copy_success = True
                            except Exception as e:
                                print(f"Copy messages failed for album {album_mids}: {e}")
                        if not copy_success and item and item.get('urls'):
                            try:
                                photo_urls = item.get('urls', [item.get('url')])
                                caption_text = html.escape(item.get('text', '')[:800])
                                author = item.get('screen_name', 'unknown')
                                author_label = f"@{author}" if author != 'unknown' else "Link to Tweet"
                                src_num = item.get('source_list_num')
                                list_label = f" • <i>List {src_num}</i>" if src_num else ""
                                cap = f"{caption_text}\n\n<a href='{item.get('tweet_url')}'>{author_label}</a>{list_label}"
                                input_media = [
                                    InputMediaPhoto(media=u, caption=cap, parse_mode="HTML")
                                    if i == 0 else InputMediaPhoto(media=u)
                                    for i, u in enumerate(photo_urls)
                                ]
                                await context.bot.send_media_group(chat_id=channel_id, media=input_media)
                                copy_success = True
                            except Exception as e:
                                print(f"Direct album send to channel failed: {e}")
                    else:
                        if "Choose action:" not in msg_text:
                            try:
                                await context.bot.copy_message(
                                    chat_id=channel_id,
                                    from_chat_id=chat_id,
                                    message_id=msg_id_int
                                )
                                copy_success = True
                            except Exception as e:
                                print(f"Copy to channel failed: {e}")
                except Exception as e:
                    print(f"Error in _do_like_transfer: {e}")
                finally:
                    if copy_success:
                        # Clean up album media messages in parallel (Finding 5)
                        if is_album_control and album_mids:
                            await asyncio.gather(
                                *[context.bot.delete_message(chat_id=chat_id, message_id=mid) for mid in album_mids],
                                return_exceptions=True
                            )
                        # Clean up interactive control message
                        await cleanup_reviewed_message(query, "like")
                    else:
                        # Report failure so item is not silently lost (Finding 3)
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="⚠️ Failed to copy item to your channel! Please verify channel ID and bot admin rights."
                            )
                        except Exception:
                            pass

            transfer_task = asyncio.create_task(_do_like_transfer())
            _active_background_tasks.add(transfer_task)
            transfer_task.add_done_callback(_active_background_tasks.discard)

            review_dict.pop(msg_id_str, None)
            review_dict.pop(msg_id_int, None)
            unreviewed_count = max(0, unreviewed_count - 1)
            save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, review_dict, keys={"bot_stats", "unreviewed_count", "review_dict"})
                
        elif action == "skip":
            bot_stats["skipped"] = bot_stats.get("skipped", 0) + 1
            if item:
                last_skipped = item
                
            # Immediately strip buttons to prevent duplicate taps (Finding 1)
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
                
            # Clean up album media messages in parallel (Finding 5)
            if is_album_control and album_mids:
                await asyncio.gather(
                    *[context.bot.delete_message(chat_id=chat_id, message_id=mid) for mid in album_mids],
                    return_exceptions=True
                )
                
            await cleanup_reviewed_message(query, "skip")
            review_dict.pop(msg_id_str, None)
            review_dict.pop(msg_id_int, None)
            unreviewed_count = max(0, unreviewed_count - 1)
            save_data(tweet_queue, history, unreviewed_count, media_filter, custom_cookies, include_retweets, custom_list_url, bot_stats, review_dict, keys={"bot_stats", "unreviewed_count", "review_dict"})
            
        elif action == "pause":
            # Stop any active drip feeds
            if context.job_queue:
                current_jobs = context.job_queue.get_jobs_by_name(str(query.message.chat_id))
                for job in current_jobs:
                    job.schedule_removal()
                    
            # Remove the pause button from this message to show it's paused
            new_keyboard = []
            if query.message.reply_markup:
                for row in query.message.reply_markup.inline_keyboard:
                    new_row = [btn for btn in row if btn.callback_data != "pause"]
                    if new_row:
                        new_keyboard.append(new_row)
            if not new_keyboard:
                new_keyboard = [
                    [
                        InlineKeyboardButton("❤️ Save", callback_data="like"),
                        InlineKeyboardButton("👎 Skip", callback_data="skip")
                    ]
                ]
            await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
                    
            await context.bot.send_message(chat_id=query.message.chat_id, text="⏸️ Paused! (Auto-drip stopped). The video above is safely in your chat history—just Love/Skip it when you're ready to continue.")
            return

        elif action.startswith("switch_list:"):
            target = action.split(":")[1]
            if target == "2" and not list2_url:
                await query.answer("List 2 is not configured yet! Use /list2 <url>", show_alert=True)
                return
            active_list = target
            save_lists()
            custom_list_url = get_active_list_url()
            await query.answer(f"Switched to List {active_list}!")
            l1_disp = list1_url if list1_url else "Not configured"
            l2_disp = list2_url if list2_url else "Not configured (set with /list2 <url>)"
            msg = "📋 <b>Twitter Lists</b>\n\n"
            msg += f"1️⃣ <b>List 1:</b> {l1_disp} {'<b>[ACTIVE ✅]</b>' if active_list == '1' else ''}\n\n"
            msg += f"2️⃣ <b>List 2:</b> {l2_disp} {'<b>[ACTIVE ✅]</b>' if active_list == '2' else ''}\n\n"
            msg += f"Current scraping source: <b>List {active_list}</b>\n\n"
            msg += "<i>Commands:</i>\n"
            msg += "• <code>/list1 [url]</code>\n"
            msg += "• <code>/list2 [url]</code>\n"
            msg += "• <code>/switchlist</code> (toggle)"
            keyboard = [
                [
                    InlineKeyboardButton("✅ List 1" if active_list == "1" else "▶️ Switch to List 1", callback_data="switch_list:1"),
                    InlineKeyboardButton("✅ List 2" if active_list == "2" else "▶️ Switch to List 2", callback_data="switch_list:2"),
                ],
                [
                    InlineKeyboardButton("🔄 Scrape Active List", callback_data="scrape_active")
                ]
            ]
            try:
                await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            except Exception:
                pass
            return

        elif action == "scrape_active":
            await query.answer("Starting scrape...")
            await do_scrape(context, query.message.chat_id, target_count=50)
            if tweet_queue:
                asyncio.ensure_future(fill_buffer(chat_id, context))
            return

        # Automatically fill the buffer back up to 5 as a background task
        asyncio.ensure_future(fill_buffer(chat_id, context))
    except Exception as e:
        print(f"Error in button_handler: {e}")
        import traceback
        traceback.print_exc()
async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = str(update.channel_post.chat.id)
    config['telegram_channel_id'] = channel_id
    os.environ['TELEGRAM_CHANNEL_ID'] = channel_id
    print(f"Auto-detected Channel ID: {channel_id}")

async def post_shutdown(application: Application):
    if _active_background_tasks:
        print(f"Waiting for {len(_active_background_tasks)} pending background tasks to finish...")
        await asyncio.gather(*_active_background_tasks, return_exceptions=True)
    if _storage_executor:
        _storage_executor.shutdown(wait=True)

async def post_init(application: Application):
    try:
        await application.bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        print(f"Failed to delete webhook during post_init: {e}")
    application.job_queue.run_repeating(auto_scrape_job, interval=3600, first=60)
    await application.bot.set_my_commands([
        ("lists", "View and switch between your 2 Twitter lists"),
        ("list1", "Switch to or set List 1 (e.g. /list1 or /list1 <url>)"),
        ("list2", "Switch to or set List 2 (e.g. /list2 or /list2 <url>)"),
        ("switchlist", "Toggle between List 1 and List 2"),
        ("setlist", "Switch or set Twitter List URL"),
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
        
    app = ApplicationBuilder().token(config['telegram_bot_token']).read_timeout(60.0).write_timeout(60.0).connect_timeout(60.0).pool_timeout(60.0).post_init(post_init).post_shutdown(post_shutdown).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lists", lists_command))
    app.add_handler(CommandHandler("list1", list1_command))
    app.add_handler(CommandHandler("l1", list1_command))
    app.add_handler(CommandHandler("list2", list2_command))
    app.add_handler(CommandHandler("l2", list2_command))
    app.add_handler(CommandHandler("switchlist", switchlist_command))
    app.add_handler(CommandHandler("switch", switchlist_command))
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
    
    if PUBLIC_URL:
        webhook_url = f"{PUBLIC_URL.rstrip('/')}/{config['telegram_bot_token']}"
        print(f"Starting webhook on port {PORT}...")
        print(f"Webhook URL: {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=config['telegram_bot_token'],
            webhook_url=webhook_url,
        )
    else:
        print("PUBLIC_URL not configured. Running in polling mode...")
        app.run_polling(drop_pending_updates=False)

if __name__ == '__main__':
    main()