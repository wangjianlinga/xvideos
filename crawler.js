const xvideos = require('./lib');
const { saveVideos } = require('./lib/db');

const TARGET_PAGES = process.argv[2] ? parseInt(process.argv[2], 10) : 1;

(async () => {
  try {
    console.log(`Starting crawl of ${TARGET_PAGES} page(s)...`);

    let currentPage = 1;
    let hasMore = true;
    let totalSaved = 0;

    while (hasMore && currentPage <= TARGET_PAGES) {
      console.log(`Fetching page ${currentPage}...`);
      const result = await xvideos.videos.fresh({ page: currentPage });

      if (result.videos && result.videos.length > 0) {
        // Fetch detail files for each video
        for (let i = 0; i < result.videos.length; i++) {
          const video = result.videos[i];
          try {
            console.log(`  Fetching details for video ${i + 1}/${result.videos.length}: ${video.title}`);
            const details = await xvideos.videos.details({ url: video.url });
            console.log('details: ' + JSON.stringify(details));
            video.files = details.files;
          } catch (err) {
            console.warn(`  Warning: Failed to fetch details for ${video.url}: ${err.message}`);
          }
        }

        const saved = saveVideos(result.videos, currentPage);
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
