## Recent Codenames
- **Vesper-Guard** (v1.13.4): Persisted `review_dict` in Apify KV store and added deterministic fallback reconstruction for Telegram album media IDs across Render sleep cycles.
- **Zephyr-Flow** (v1.13.3): Resolved UnboundLocalError on `custom_list_url` in `button_handler`, restored auto-refill of the 5-card screen buffer on Like/Skip, and added global fallbacks in `save_data`.
- **Aura-Stream** (v1.13.2): Resolved UnboundLocalError on `tweet_queue` in `send_next_tweet`, added user feedback for filling states, allowed manual `/next` while drip feed is active, and added top-level error reporting to command handlers.
- **Prism-Flow** (v1.13.1): Purgequeue history liberation to allow immediate re-scraping, feedback notifications on `/next` for empty queue or full review buffer, and targeted Apify KV save keys.
- **Opal-Gallery** (v1.13.0): Bundled multi-photo album support across Telegram bot (`send_media_group` with follow-up action controls) and web player (interactive photo carousel with pagination dots), caption sanitization of trailing `t.co` media links, and atomic channel saving.

