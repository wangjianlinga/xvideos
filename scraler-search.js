const xvideos = require('./lib');
const { saveVideos } = require('./lib/db');

const TARGET_PAGES = process.argv[2] ? parseInt(process.argv[2], 10) : 1;
const KEYWORD = process.env.CRAWL_KEYWORD || process.argv[3] || 'threesome';

(async () => {
  try {
    console.log(`Starting search crawl for "${KEYWORD}", ${TARGET_PAGES} page(s)...`);

    let currentPage = 1;
    let hasMore = true;
    let totalSaved = 0;

    while (hasMore && currentPage <= TARGET_PAGES) {
      console.log(`Fetching page ${currentPage}...`);
      const result = await xvideos.videos.search({
        page: currentPage,
        k: KEYWORD
      });

      if (result.videos && result.videos.length > 0) {
        const saved = saveVideos(result.videos, currentPage, 'search');
        totalSaved += saved;
        console.log(`  Saved ${saved} videos from page ${currentPage}`);
      } else {
        console.log(`  No videos found on page ${currentPage}`);
      }

      hasMore = result.hasNext();
      currentPage++;
    }

    console.log(`Crawl complete. Total videos saved: ${totalSaved}`);
    process.exit(0);
  } catch (err) {
    console.error('Crawl failed:', err.message);
    process.exit(1);
  }
})();
