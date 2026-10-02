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

    let queue = (qRec?.value as unknown as MediaItem[]) || [];
    let stats = (sRec?.value as unknown as BotStats) || { loved: 0, skipped: 0 };

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
      store.setRecord({ key: 'queue', value: queue as any }),
      store.setRecord({ key: 'bot_stats', value: stats as any }),
    ]);

    return NextResponse.json({ success: true, remainingCount: queue.length });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
