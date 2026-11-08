import { NextRequest, NextResponse } from 'next/server';
import { getStoreClient } from '@/lib/apify';
import { MediaItem, BotStats } from '@/lib/types';
import { getCachedQueue, setCachedQueue } from '@/lib/cache';

export const dynamic = 'force-dynamic';

function sanitizeMediaItem(raw: any): MediaItem {
  return {
    tweet_url: String(raw.tweet_url || ''),
    text: String(raw.text || '').slice(0, 800),
    screen_name: raw.screen_name ? String(raw.screen_name) : undefined,
    type: raw.type === 'video' || raw.type === 'album' ? raw.type : 'photo',
    url: String(raw.url || ''),
    urls: Array.isArray(raw.urls) ? raw.urls.map(String) : undefined,
    width: typeof raw.width === 'number' ? raw.width : undefined,
    height: typeof raw.height === 'number' ? raw.height : undefined,
    duration_millis: typeof raw.duration_millis === 'number' ? raw.duration_millis : undefined,
    source_list: raw.source_list ? String(raw.source_list) : undefined,
    source_list_num: raw.source_list_num ? String(raw.source_list_num) : undefined,
  };
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const limit = parseInt(searchParams.get('limit') || '30', 10);
    const offset = parseInt(searchParams.get('offset') || '0', 10);

    const cached = getCachedQueue<any>();
    if (cached) {
      const paged = cached.queue.slice(offset, offset + limit);
      return NextResponse.json(
        {
          ...cached,
          queue: paged,
          totalCount: cached.queue.length,
          hasMore: offset + limit < cached.queue.length,
          fromCache: true,
        },
        {
          headers: {
            'Cache-Control': 'public, s-maxage=3, stale-while-revalidate=15',
          },
        }
      );
    }

    const store = await getStoreClient();
    const [qRec, sRec, fRec, actRec, l1Rec, l2Rec] = await Promise.all([
      store.getRecord('queue'),
      store.getRecord('bot_stats'),
      store.getRecord('media_filter'),
      store.getRecord('active_list'),
      store.getRecord('list1_url'),
      store.getRecord('list2_url'),
    ]);

    const rawQueue = (qRec?.value as unknown as any[]) || [];
    const stats = (sRec?.value as unknown as BotStats) || { loved: 0, skipped: 0 };
    const mediaFilter = (fRec?.value as unknown as string) || 'all';

    const sanitizedQueue = rawQueue.map(sanitizeMediaItem);

    const filteredQueue =
      mediaFilter === 'all'
        ? sanitizedQueue
        : mediaFilter === 'photo'
        ? sanitizedQueue.filter(item => item.type === 'photo' || item.type === 'album')
        : sanitizedQueue.filter(item => item.type === 'video');

    const cachePayload = {
      queue: filteredQueue,
      stats,
      media_filter: mediaFilter,
      mediaFilter,
      active_list: String(actRec?.value || '1'),
      list1_url: String(l1Rec?.value || ''),
      list2_url: String(l2Rec?.value || ''),
    };

    setCachedQueue(cachePayload);

    const paged = filteredQueue.slice(offset, offset + limit);

    return NextResponse.json(
      {
        ...cachePayload,
        queue: paged,
        totalCount: filteredQueue.length,
        hasMore: offset + limit < filteredQueue.length,
        fromCache: false,
      },
      {
        headers: {
          'Cache-Control': 'public, s-maxage=3, stale-while-revalidate=15',
        },
      }
    );
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
