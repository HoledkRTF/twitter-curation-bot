import json
import os
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apify_client import ApifyClient
from playwright.async_api import async_playwright

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
    store_client = apify_client.key_value_store(store['id'])
except Exception as e:
    print(f"Failed to connect to Apify KV Store: {e}")
    store_client = None

def load_data():
    tweet_queue = []
    history = []
    if store_client:
        q_rec = store_client.get_record("queue")
        if q_rec and q_rec.get('value'):
            tweet_queue = q_rec['value']
            
        h_rec = store_client.get_record("history")
        if h_rec and h_rec.get('value'):
            history = h_rec['value']
    return tweet_queue, history

def save_data(tweet_queue, history):
    if store_client:
        store_client.set_record("queue", tweet_queue)
        store_client.set_record("history", history)

tweet_queue, history = load_data()

async def extract_media_from_twitter(url):
    extracted_items = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        
        await context.add_cookies([
            {"name": "auth_token", "value": config['twitter_auth_token'], "domain": ".x.com", "path": "/"},
            {"name": "ct0", "value": config['twitter_ct0'], "domain": ".x.com", "path": "/"}
        ])
        
        page = await context.new_page()
        
        graphql_hits = []
        
        async def handle_response(response):
            url = response.url
            # Log all graphql hits for debugging
            if "graphql" in url:
                endpoint = url.split("/")[-1].split("?")[0]
                graphql_hits.append(endpoint)
                
            if "graphql" in url and ("ListLatestTweetsTimeline" in url or "ListLatest" in url):
                try:
                    data = await response.json()
                    instructions = data.get('data', {}).get('list', {}).get('tweets_timeline', {}).get('timeline', {}).get('instructions', [])
                    for inst in instructions:
                        if inst.get('type') == 'TimelineAddEntries':
                            for entry in inst.get('entries', []):
                                content = entry.get('content', {})
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
                                                best = max(mp4s, key=lambda x: x.get('bitrate', 0))
                                                media_obj['url'] = best['url']
                                                media_obj['type'] = 'video'
                                                extracted_items.append(media_obj)
                                        elif m.get('type') == 'photo':
                                            media_obj['url'] = m['media_url_https']
                                            media_obj['type'] = 'photo'
                                            extracted_items.append(media_obj)
                except Exception as e:
                    print(f"Error parsing graphql response: {e}")

        page.on("response", handle_response)
        
        print(f"Navigating to {url}...")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        
        title = await page.title()
        current_url = page.url
        print(f"Page title: {title}")
        print(f"Current URL: {current_url}")
        
        # Wait for GraphQL responses to come in, then scroll for more
        await asyncio.sleep(5)
        for _ in range(5):
            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(3)
        
        print(f"GraphQL endpoints hit: {graphql_hits}")
        print(f"Extracted items: {len(extracted_items)}")
            
        await browser.close()
    return extracted_items

async def do_scrape(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    await context.bot.send_message(chat_id=chat_id, text="🚀 Firing up custom Chromium scraper... (This takes about 20 seconds)")
    
    try:
        if not config['twitter_auth_token'] or not config['twitter_ct0']:
            await context.bot.send_message(chat_id=chat_id, text="Error: Missing Twitter cookies in environment variables!")
            return
            
        items = await extract_media_from_twitter(config['twitter_list_url'])
        
        count = 0
        for item in items:
            if item['url'] not in history and not any(q.get('url') == item['url'] for q in tweet_queue):
                tweet_queue.append(item)
                history.append(item['url'])
                count += 1
                
        save_data(tweet_queue, history)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Scraped {len(items)} posts, found {count} brand new ones! Total in queue: {len(tweet_queue)}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Error scraping: {e}")

async def scrape_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_scrape(context, update.message.chat_id)
    if tweet_queue:
        await send_next_tweet(update.message.chat_id, context)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history.clear()
    save_data(tweet_queue, history)
    await update.message.reply_text("🗑️ History cleared! The scraper will now re-fetch older tweets as if they were brand new.")

async def fetch_media(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.content

async def send_next_tweet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not tweet_queue:
        await do_scrape(context, chat_id)
        if not tweet_queue:
            await context.bot.send_message(chat_id=chat_id, text="Still empty! Try scraping again later when the Twitter list has new posts.")
            return

    next_item = tweet_queue[0]
    
    keyboard = [
        [
            InlineKeyboardButton("👍 Like (Save to Channel)", callback_data="like"),
            InlineKeyboardButton("👎 Skip", callback_data="skip")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    caption = f"{next_item['text'][:800]}\n\n[Link to Tweet]({next_item['tweet_url']})"
    
    status_msg = await context.bot.send_message(chat_id=chat_id, text="Loading next item...")
    try:
        media_bytes = await fetch_media(next_item['url'])
        
        if next_item['type'] == 'photo':
            await context.bot.send_photo(chat_id=chat_id, photo=media_bytes, caption=caption, reply_markup=reply_markup)
        else:
            await context.bot.send_video(chat_id=chat_id, video=media_bytes, caption=caption, reply_markup=reply_markup)
            
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"Error downloading/sending media: {e}\nURL: {next_item['url']}", reply_markup=reply_markup)

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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if not tweet_queue:
        await query.message.reply_text("Queue is empty.")
        return
        
    current_item = tweet_queue.pop(0)
    save_data(tweet_queue, history)
    
    if action == "like":
        channel_id = config.get('telegram_channel_id')
        if not channel_id:
            await query.message.reply_text("Error: You haven't set a Channel ID yet! Use /channel <id>")
            tweet_queue.insert(0, current_item)
            save_data(tweet_queue, history)
            return
            
        try:
            await context.bot.copy_message(
                chat_id=channel_id,
                from_chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
            await query.message.delete()
        except Exception as e:
            await query.message.reply_text(f"Failed to post to channel: {e}")
            tweet_queue.insert(0, current_item)
            save_data(tweet_queue, history)
            return
            
    elif action == "skip":
        await query.message.delete()

    if context.job_queue:
        current_jobs = context.job_queue.get_jobs_by_name(str(query.message.chat_id))
        if not current_jobs:
            await send_next_tweet(query.message.chat_id, context)
    else:
        await send_next_tweet(query.message.chat_id, context)

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
