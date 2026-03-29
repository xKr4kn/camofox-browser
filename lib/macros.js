const MACROS = {
  '@google_search': (query) => `https://www.google.com/search?q=${encodeURIComponent(query || '')}`,
  '@youtube_search': (query) => `https://www.youtube.com/results?search_query=${encodeURIComponent(query || '')}`,
  '@amazon_search': (query) => `https://www.amazon.com/s?k=${encodeURIComponent(query || '')}`,
  '@reddit_search': (query) => `https://www.reddit.com/search.json?q=${encodeURIComponent(query || '')}&limit=25`,
  '@reddit_subreddit': (query) => `https://www.reddit.com/r/${encodeURIComponent(query || 'all')}.json?limit=25`,
  '@wikipedia_search': (query) => `https://en.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(query || '')}`,
  '@twitter_search': (query) => `https://twitter.com/search?q=${encodeURIComponent(query || '')}`,
  '@yelp_search': (query) => `https://www.yelp.com/search?find_desc=${encodeURIComponent(query || '')}`,
  '@spotify_search': (query) => `https://open.spotify.com/search/${encodeURIComponent(query || '')}`,
  '@netflix_search': (query) => `https://www.netflix.com/search?q=${encodeURIComponent(query || '')}`,
  '@linkedin_search': (query) => `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(query || '')}`,
  '@instagram_search': (query) => `https://www.instagram.com/explore/tags/${encodeURIComponent(query || '')}`,
  '@tiktok_search': (query) => `https://www.tiktok.com/search?q=${encodeURIComponent(query || '')}`,
  '@twitch_search': (query) => `https://www.twitch.tv/search?term=${encodeURIComponent(query || '')}`,
  '@perplexity_search': (query) => `https://www.perplexity.ai/?q=${encodeURIComponent(query || '')}`,
  '@phind_search': (query) => `https://www.phind.com/search?q=${encodeURIComponent(query || '')}`,
  '@brave_search': (query) => `https://search.brave.com/search?q=${encodeURIComponent(query || '')}`,
  '@kagi_search': (query) => `https://kagi.com/search?q=${encodeURIComponent(query || '')}`,
  '@bing_search': (query) => `https://www.bing.com/search?q=${encodeURIComponent(query || '')}`,
  '@yahoo_search': (query) => `https://search.yahoo.com/search?p=${encodeURIComponent(query || '')}`,
  '@deepl_search': (query) => `https://www.deepl.com/translator#auto/en/${encodeURIComponent(query || '')}`,
  '@arxiv_search': (query) => `https://arxiv.org/search/?search-type=all&sortby=relevance&query=${encodeURIComponent(query || '')}`,
  '@crossmark_search': (query) => `https://api.crossmark.io/v1/search?query=${encodeURIComponent(query || '')}`,
  '@github_search': (query) => `https://github.com/search?q=${encodeURIComponent(query || '')}&type=repositories`,
  '@hackernews_search': (query) => `https://hn.algolia.com/?q=${encodeURIComponent(query || '')}&sort=relevance`,
  '@producthunt_search': (query) => `https://www.producthunt.com/search?q=${encodeURIComponent(query || '')}`,
  '@scholar_search': (query) => `https://scholar.google.com/scholar?q=${encodeURIComponent(query || '')}`,
  '@news_search': (query) => `https://news.google.com/search?q=${encodeURIComponent(query || '')}`,
  '@google_news': (query) => `https://news.google.com/search?q=${encodeURIComponent(query || '')}`,
  '@HN_frontpage': () => `https://news.ycombinator.com/`
};

function expandMacro(macro, query) {
  const macroFn = MACROS[macro];
  return macroFn ? macroFn(query) : null;
}

function getSupportedMacros() {
  return Object.keys(MACROS);
}

export {
  expandMacro,
  getSupportedMacros,
  MACROS
};
