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

    const queue = (qRec?.value as unknown as MediaItem[]) || [];
    const stats = (sRec?.value as unknown as BotStats) || { loved: 0, skipped: 0 };
    const mediaFilter = (fRec?.value as unknown as string) || 'all';

    const filteredQueue = mediaFilter !== 'all' ? queue.filter(item => item.type === mediaFilter) : queue;

    return NextResponse.json({ queue: filteredQueue, stats, media_filter: mediaFilter, mediaFilter });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
