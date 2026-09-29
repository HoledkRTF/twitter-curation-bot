import json
from apify_client import ApifyClient

with open('config.json', 'r') as f:
    config = json.load(f)

client = ApifyClient(config['apify_api_token'])

print("Starting Twitter scraper...")
run = client.actor("apidojo/tweet-scraper").call(run_input={
    "startUrls": [{"url": config['twitter_list_url']}],
    "tweetsDesired": 10
})

dataset_id = run.default_dataset_id if hasattr(run, 'default_dataset_id') else run['defaultDatasetId']

print("Scraping finished. Fetching results...")
results = []
for item in client.dataset(dataset_id).iterate_items():
    print(item.keys())
    results.append(item)
    break
    if item.get('extendedEntities') and item['extendedEntities'].get('media'):
        results.append(item)

print(f"Found {len(results)} tweets with media!")
if results:
    print("Sample media URL:", results[0]['extendedEntities']['media'][0]['media_url_https'])
