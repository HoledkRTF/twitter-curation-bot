import os
from apify_client import ApifyClient
import time

TOKEN = "apify_api_zkccbeiDQQ0gKBLfLgaP62xYQq6tAI09zTLg"
client = ApifyClient(TOKEN)

print("Starting test run with microworlds/twitter-scraper...")
run = client.actor("microworlds/twitter-scraper").call(run_input={
    "searchTerms": ["list:2078086710118715619 filter:media"],
    "maxItems": 50,
})

dataset_id = getattr(run, 'default_dataset_id', None) or run.get('defaultDatasetId')
dataset = client.dataset(dataset_id)
items = dataset.list_items().items

print(f"Dataset items: {len(items)}")
c = sum(1 for i in items if isinstance(i, dict) and (i.get('extendedEntities') or i.get('media')))
print(f"Items with media: {c}")
