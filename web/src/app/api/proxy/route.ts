import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get('url');
  if (!url) {
    return new NextResponse('Missing url parameter', { status: 400 });
  }

  try {
    const parsed = new URL(url);
    if (!parsed.hostname.endsWith('twimg.com')) {
      return new NextResponse('Invalid target host', { status: 403 });
    }
  } catch {
    return new NextResponse('Invalid url', { status: 400 });
  }

  try {
    const range = req.headers.get('range');
    const headers: Record<string, string> = {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
      'Referer': 'https://twitter.com/',
      'Accept': '*/*',
    };
    if (range) {
      headers['Range'] = range;
    }

    const upstream = await fetch(url, { headers });

    const responseHeaders = new Headers();
    const headersToCopy = ['content-type', 'content-length', 'content-range', 'accept-ranges'];
    headersToCopy.forEach(h => {
      const val = upstream.headers.get(h);
      if (val) responseHeaders.set(h, val);
    });
    responseHeaders.set('Access-Control-Allow-Origin', '*');
    responseHeaders.set('Cache-Control', 'public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800');

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (err: any) {
    return new NextResponse(err.message || 'Proxy error', { status: 500 });
  }
}
