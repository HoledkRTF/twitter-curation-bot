import json
import os
import html
import asyncio
import httpx
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
            
    return tweet_queue, history, unreviewed_count

def save_data(tweet_queue, history, unreviewed_count):
    if store_client:
        store_client.set_record("queue", tweet_queue)
        store_client.set_record("history", history)
        store_client.set_record("unreviewed_count", unreviewed_count)

tweet_queue, history, unreviewed_count = load_data()

async def extract_media_from_twitter(list_id):
    extracted_items = []
    
    headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": config['twitter_ct0'],
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    
    cookies = {
        "auth_token": config['twitter_auth_token'],
        "ct0": config['twitter_ct0']
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
    
    async with httpx.AsyncClient() as client:
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
                    print(f"Twitter API Error: {res.status_code} - {res.text[:200]}")
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
                                
                                if 'retweeted_status_result' in tweet:
                                    tweet = tweet['retweeted_status_result']['result'].get('legacy', {})
                                    
                                media = tweet.get('extended_entities', {}).get('media', [])
                                
                                for m in media:
                                    media_obj = {'tweet_url': tweet_url, 'text': tweet_text}
                                    if m.get('type') in ['video', 'animated_gif']:
                                        variants = m.get('video_info', {}).get('variants', [])
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
                break
                
    return extracted_items

async def do_scrape(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    global tweet_queue, history, unreviewed_count
    await context.bot.send_message(chat_id=chat_id, text="🔄 Scraping Twitter list...")
    
    try:
        if not config['twitter_auth_token'] or not config['twitter_ct0']:
            await context.bot.send_message(chat_id=chat_id, text="Error: Missing Twitter cookies in environment variables!")
            return
            
        # Extract numeric list ID from URL like https://x.com/i/lists/2078086710118715619
        list_url = config['twitter_list_url']
        list_id = list_url.rstrip('/').split('/')[-1]
        items = await extract_media_from_twitter(list_id)
        
        count = 0
        added_items = []
        for item in items:
            if item['url'] not in history and not any(q.get('url') == item['url'] for q in tweet_queue):
                added_items.append(item)
                history.append(item['url'])
                count += 1
                
        # Prepend new items so the freshest media is served first
        tweet_queue = added_items + tweet_queue
        
        save_data(tweet_queue, history, unreviewed_count)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Scraped {len(items)} posts, found {count} brand new ones! Total in queue: {len(tweet_queue)}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Error scraping: {e}")

async def scrape_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_scrape(context, update.message.chat_id)
    if tweet_queue:
        await send_next_tweet(update.message.chat_id, context)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count
    history.clear()
    unreviewed_count = 0
    save_data(tweet_queue, history, unreviewed_count)
    await update.message.reply_text("🗑️ History cleared! The scraper will now re-fetch older tweets as if they were brand new.")

async def fetch_media(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=180.0)
        response.raise_for_status()
        return response.content

async def upload_to_gofile(file_bytes, filename="video.mp4"):
    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.get("https://api.gofile.io/servers")
        server = res.json()['data']['servers'][0]['name']
        files = {'file': (filename, file_bytes)}
        upload_res = await client.post(f"https://{server}.gofile.io/contents/uploadfile", files=files)
        return upload_res.json()['data']['downloadPage']

VERSION = "v1.6.4"

async def send_next_tweet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not tweet_queue:
        await do_scrape(context, chat_id)
        if not tweet_queue:
            await context.bot.send_message(chat_id=chat_id, text="Still empty! Try scraping again later when the Twitter list has new posts.")
            return

    global unreviewed_count
    
    next_item = tweet_queue.pop(0)
    save_data(tweet_queue, history, unreviewed_count)
    
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
    
    safe_text = html.escape(next_item['text'][:800])
    caption = f"{safe_text}\n\n<a href='{next_item['tweet_url']}'>Link to Tweet</a>\n\n<code>{VERSION}</code>"
    
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Loading next item...")
    try:
        media_bytes = None
        urls_to_try = next_item.get('urls', [next_item['url']])
        
        highest_bytes = await fetch_media(urls_to_try[0])
        
        if len(highest_bytes) > 50_000_000:
            await status_msg.edit_text("Uploading full-res to Gofile (too large for Telegram)...")
            try:
                gofile_link = await upload_to_gofile(highest_bytes)
                caption += f"\n\n⚠️ <b>DOWNSCALED PREVIEW</b> (Original exceeds Telegram's 50MB limit)\n📥 <a href='{gofile_link}'>Download Full-Res (Gofile)</a>"
            except Exception as e:
                print(f"Gofile upload failed: {e}")
                caption += f"\n\n⚠️ <b>DOWNSCALED PREVIEW</b> (Original exceeds Telegram's 50MB limit, Gofile upload failed)"
                
            for u in urls_to_try[1:]:
                try:
                    temp_bytes = await fetch_media(u)
                    if len(temp_bytes) <= 50_000_000:
                        media_bytes = temp_bytes
                        break
                except Exception:
                    continue
        else:
            media_bytes = highest_bytes
                
        if not media_bytes or len(media_bytes) > 50_000_000:
            fallback_msg = f"⚠️ <b>Video too large for Telegram natively (>50MB).</b>\n🔗 <a href='{next_item['url']}'>Direct Media Link</a>\n\n{caption}"
            await context.bot.send_message(chat_id=chat_id, text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
            unreviewed_count += 1
            save_data(tweet_queue, history, unreviewed_count)
            await status_msg.delete()
            return

        if next_item['type'] == 'photo':
            await context.bot.send_photo(chat_id=chat_id, photo=media_bytes, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await context.bot.send_video(chat_id=chat_id, video=media_bytes, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            
        unreviewed_count += 1
        save_data(tweet_queue, history, unreviewed_count)
        await status_msg.delete()
    except Exception as e:
        print(f"Error downloading/sending media: {e}")
        fallback_msg = f"⚠️ <b>Media download failed (Timeout/Error).</b>\n🔗 <a href='{next_item['url']}'>Direct Media Link</a>\n\n{caption}"
        await status_msg.edit_text(text=fallback_msg, reply_markup=reply_markup, parse_mode="HTML")
        unreviewed_count += 1
        save_data(tweet_queue, history, unreviewed_count)

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

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_next_tweet(update.message.chat_id, context)

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(VERSION)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global unreviewed_count
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == "like":
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
            await query.message.delete()
            unreviewed_count = max(0, unreviewed_count - 1)
            save_data(tweet_queue, history, unreviewed_count)
        except Exception as e:
            await query.message.reply_text(f"Failed to post to channel: {e}")
            return
            
    elif action == "skip":
        await query.message.delete()
        unreviewed_count = max(0, unreviewed_count - 1)
        save_data(tweet_queue, history, unreviewed_count)
        
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

    # Fire replacement as background task so this handler returns instantly
    should_replace = unreviewed_count < 5
    if should_replace:
        if context.job_queue:
            current_jobs = context.job_queue.get_jobs_by_name(str(query.message.chat_id))
            if current_jobs:
                should_replace = False
    if should_replace:
        asyncio.ensure_future(send_next_tweet(query.message.chat_id, context))

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = str(update.channel_post.chat.id)
    config['telegram_channel_id'] = channel_id
    os.environ['TELEGRAM_CHANNEL_ID'] = channel_id
    print(f"Auto-detected Channel ID: {channel_id}")

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("next", "Load the next item in the queue"),
        ("scrape", "Force a manual scrape for more media"),
        ("drip", "Auto-send media on a schedule (e.g. /drip 10)"),
        ("stopdrip", "Stop auto-sending"),
        ("clearhistory", "Wipe the scraper's memory so you can see old tweets again"),
        ("channel", "Set your private channel ID"),
        ("v", "Check current bot version"),
    ])

def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    app = ApplicationBuilder().token(config['telegram_bot_token']).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scrape", scrape_tweets))
    app.add_handler(CommandHandler("clearhistory", clear_history))
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("v", version_command))
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
