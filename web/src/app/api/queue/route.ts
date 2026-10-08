import { NextResponse } from 'next/server';
import { getStoreClient } from '@/lib/apify';
import { MediaItem, BotStats } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const store = await getStoreClient();
    const [qRec, sRec, fRec, actRec, l1Rec, l2Rec] = await Promise.all([
      store.getRecord('queue'),
      store.getRecord('bot_stats'),
      store.getRecord('media_filter'),
      store.getRecord('active_list'),
      store.getRecord('list1_url'),
      store.getRecord('list2_url'),
    ]);

    const queue = (qRec?.value as unknown as MediaItem[]) || [];
    const stats = (sRec?.value as unknown as BotStats) || { loved: 0, skipped: 0 };
    const mediaFilter = (fRec?.value as unknown as string) || 'all';

    const filteredQueue =
      mediaFilter === 'all'
        ? queue
        : mediaFilter === 'photo'
        ? queue.filter(item => item.type === 'photo' || item.type === 'album')
        : queue.filter(item => item.type === 'video');

    return NextResponse.json({
      queue: filteredQueue,
      stats,
      media_filter: mediaFilter,
      mediaFilter,
      active_list: String(actRec?.value || '1'),
      list1_url: String(l1Rec?.value || ''),
      list2_url: String(l2Rec?.value || ''),
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
