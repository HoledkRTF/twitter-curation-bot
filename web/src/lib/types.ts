export interface MediaItem {
  tweet_url: string;
  text: string;
  screen_name?: string;
  type: 'video' | 'photo' | 'album';
  url: string;
  urls?: string[];
  width?: number;
  height?: number;
  duration_millis?: number;
  source_list?: string;
  source_list_num?: string;
}

export interface BotStats {
  loved: number;
  skipped: number;
}
