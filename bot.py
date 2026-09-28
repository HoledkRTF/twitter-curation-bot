import json
import os
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apify_client import ApifyClient

# Config from environment variables
config = {
    'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'telegram_channel_id': os.environ.get('TELEGRAM_CHANNEL_ID', ''),
    'twitter_list_url': os.environ.get('TWITTER_LIST_URL', ''),
    'apify_api_token': os.environ.get('APIFY_API_TOKEN', ''),
}

QUEUE_FILE = 'queue.json'
HISTORY_FILE = 'history.json'
PORT = int(os.environ.get('PORT', 10000))
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', '')

apify_client = ApifyClient(config['apify_api_token'])

if os.path.exists(QUEUE_FILE):
    with open(QUEUE_FILE, 'r') as f:
        tweet_queue = json.load(f)
else:
    tweet_queue = []

if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'r') as f:
        history = json.load(f)
else:
    history = []

def save_queue():
    with open(QUEUE_FILE, 'w') as f:
        json.dump(tweet_queue, f)

def save_history():
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f)

async def do_scrape(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    await context.bot.send_message(chat_id=chat_id, text="🔄 Auto-scraping Twitter List to refill queue... (This takes about 60 seconds)")
    
    try:
        run = apify_client.actor("apidojo/tweet-scraper").call(run_input={
            "startUrls": [{"url": config['twitter_list_url']}],
            "tweetsDesired": 100,
        })
        
        dataset_id = run.default_dataset_id if hasattr(run, 'default_dataset_id') else run['defaultDatasetId']
        
        count = 0
        for item in apify_client.dataset(dataset_id).iterate_items():
            if item.get('extendedEntities') and item['extendedEntities'].get('media'):
                url = item.get('url', '')
                vx_url = url.replace('twitter.com', 'vxtwitter.com').replace('x.com', 'vxtwitter.com')
                
                for m in item['extendedEntities']['media']:
                    media_obj = {'tweet_url': vx_url, 'text': item.get('text', '')}
                    if m['type'] == 'photo':
                        media_obj['type'] = 'photo'
                        media_obj['url'] = m['media_url_https']
                    elif m['type'] in ['video', 'animated_gif']:
                        media_obj['type'] = 'video'
                        variants = m.get('video_info', {}).get('variants', [])
                        mp4_variants = [v for v in variants if v.get('content_type') == 'video/mp4']
                        if mp4_variants:
                            best_variant = max(mp4_variants, key=lambda x: x.get('bitrate', 0))
                            media_obj['url'] = best_variant['url']
                        else:
                            continue
                            
                    if media_obj['url'] not in history and not any(q.get('url') == media_obj['url'] for q in tweet_queue):
                        tweet_queue.append(media_obj)
                        history.append(media_obj['url'])
                        count += 1
                    
        save_queue()
        save_history()
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Added {count} new items! Total in queue: {len(tweet_queue)}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Error scraping: {e}")

async def scrape_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_scrape(context, update.message.chat_id)
    if tweet_queue:
        await send_next_tweet(update.message.chat_id, context)

async def fetch_media(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.content

async def send_next_tweet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not tweet_queue:
        await do_scrape(context, chat_id)
        if not tweet_queue:
            await context.bot.send_message(chat_id=chat_id, text="Still empty! Try scraping again later.")
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
    save_queue()
    
    if action == "like":
        channel_id = config.get('telegram_channel_id')
        if not channel_id:
            await query.message.reply_text("Error: You haven't set a Channel ID yet! Use /channel <id>")
            tweet_queue.insert(0, current_item)
            save_queue()
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
            save_queue()
            return
            
    elif action == "skip":
        await query.message.delete()

    current_jobs = context.job_queue.get_jobs_by_name(str(query.message.chat_id))
    if not current_jobs:
        await send_next_tweet(query.message.chat_id, context)

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = str(update.channel_post.chat.id)
    config['telegram_channel_id'] = channel_id
    os.environ['TELEGRAM_CHANNEL_ID'] = channel_id
    print(f"Auto-detected Channel ID: {channel_id}")

def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    app = ApplicationBuilder().token(config['telegram_bot_token']).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scrape", scrape_tweets))
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
