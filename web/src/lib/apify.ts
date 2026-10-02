import { ApifyClient } from 'apify-client';

const token = process.env.APIFY_API_TOKEN || '';
export const apifyClient = new ApifyClient({ token });

export async function getStoreClient() {
  const store = await apifyClient.keyValueStores().getOrCreate('twitter-curation-bot-storage');
  return apifyClient.keyValueStore(store.id);
}
