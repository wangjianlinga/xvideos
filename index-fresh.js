const xvideos = require('./lib');
const { saveVideos } = require('./lib/db');

(async () => {
  try {
    const targetPages = process.argv[2] ? parseInt(process.argv[2], 10) : 1;
    console.log(`Starting fresh video fetch for ${targetPages} page(s)...`);

    let currentPage = 1;
    let hasMore = true;
    let totalSaved = 0;

    while (hasMore && currentPage <= targetPages) {
      console.log(`Fetching page ${currentPage}...`);
      const fresh = await xvideos.videos.fresh({ page: currentPage });

      if (fresh.videos && fresh.videos.length > 0) {
        const saved = saveVideos(fresh.videos, currentPage);
        totalSaved += saved;
        console.log(`  Saved ${saved} videos from page ${currentPage}`);
      } else {
        console.log(`  No videos found on page ${currentPage}`);
      }

      hasMore = fresh.hasNext();
      currentPage++;
    }

    console.log(`Fetch complete. Total videos saved: ${totalSaved}`);
    process.exit(0);
  } catch (err) {
    console.error('Fetch failed:', err.message);
    process.exit(1);
  }
})();
