import { ApifyClient } from 'apify-client';

const token = process.env.APIFY_API_TOKEN || '';
export const apifyClient = new ApifyClient({ token });

let cachedStorePromise: Promise<any> | null = null;

export function getStoreClient() {
  if (!cachedStorePromise) {
    cachedStorePromise = apifyClient
      .keyValueStores()
      .getOrCreate('twitter-curation-bot-storage')
      .then(store => apifyClient.keyValueStore(store.id))
      .catch(err => {
        cachedStorePromise = null;
        throw err;
      });
  }
  return cachedStorePromise;
}
