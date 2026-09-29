import asyncio
import json
from playwright.async_api import async_playwright

auth_token = "627b310f25b01fef273fe12963c2c73a805d6ce0"
ct0 = "33d2d6a03a4d25786d15841355e8d12e26a64a30938c0634682d6f2fa7a36ca12be7106f05ccb58abf26df5d7e49a85570e2aaf2ae9dca30a0001186241294a3d5b7a88cfff2482cf2bbbdb28023f667"
list_url = "https://x.com/i/lists/2078086710118715619"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Inject cookies
        await context.add_cookies([
            {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
            {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"}
        ])
        
        page = await context.new_page()
        
        extracted_media = []
        
        async def handle_response(response):
            if "graphql" in response.url and ("ListLatestTweetsTimeline" in response.url or "ListLatest" in response.url):
                try:
                    data = await response.json()
                    # Parse the deeply nested GraphQL structure
                    instructions = data.get('data', {}).get('list', {}).get('tweets_timeline', {}).get('timeline', {}).get('instructions', [])
                    for inst in instructions:
                        if inst.get('type') == 'TimelineAddEntries':
                            for entry in inst.get('entries', []):
                                content = entry.get('content', {})
                                if content.get('entryType') == 'TimelineTimelineItem':
                                    result = content.get('itemContent', {}).get('tweet_results', {}).get('result', {})
                                    tweet = result.get('legacy', {})
                                    
                                    # Handle retweets
                                    if 'retweeted_status_result' in tweet:
                                        tweet = tweet['retweeted_status_result']['result'].get('legacy', {})
                                        
                                    media = tweet.get('extended_entities', {}).get('media', [])
                                    
                                    for m in media:
                                        if m.get('type') in ['video', 'animated_gif']:
                                            variants = m.get('video_info', {}).get('variants', [])
                                            mp4s = [v for v in variants if v.get('content_type') == 'video/mp4']
                                            if mp4s:
                                                best = max(mp4s, key=lambda x: x.get('bitrate', 0))
                                                extracted_media.append(best['url'])
                                        elif m.get('type') == 'photo':
                                            extracted_media.append(m['media_url_https'])
                except Exception as e:
                    print(f"Error parsing response: {e}")

        page.on("response", handle_response)
        
        print("Navigating to list...")
        await page.goto(list_url)
        
        print("Scrolling to load tweets...")
        for i in range(5):
            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(2)
            
        print(f"Extracted {len(extracted_media)} media files!")
        if extracted_media:
            print(f"Sample: {extracted_media[0]}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
