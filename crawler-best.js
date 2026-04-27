const xvideos = require('./lib');
const { saveVideos } = require('./lib/db');

const TARGET_YEAR = process.argv[2] || '2018';
const TARGET_MONTH = process.argv[3] || '02';
const TARGET_PAGES = process.argv[4] ? parseInt(process.argv[4], 10) : 1;

// Validate inputs
if (!/^\d{4}$/.test(TARGET_YEAR)) {
  console.error(`Invalid year: ${TARGET_YEAR}. Expected format: YYYY`);
  process.exit(1);
}
if (!/^\d{1,2}$/.test(TARGET_MONTH) || Number(TARGET_MONTH) < 1 || Number(TARGET_MONTH) > 12) {
  console.error(`Invalid month: ${TARGET_MONTH}. Expected range: 1-12`);
  process.exit(1);
}
if (isNaN(TARGET_PAGES) || TARGET_PAGES < 1) {
  console.error(`Invalid pages: ${process.argv[4]}. Expected a positive integer.`);
  process.exit(1);
}

(async () => {
  try {
    console.log(`Starting best video crawl for ${TARGET_YEAR}-${TARGET_MONTH}, ${TARGET_PAGES} page(s)...`);

    let currentPage = 1;
    let hasMore = true;
    let totalSaved = 0;

    while (hasMore && currentPage <= TARGET_PAGES) {
      console.log(`Fetching page ${currentPage}...`);
      const result = await xvideos.videos.best({ year: TARGET_YEAR, month: TARGET_MONTH, page: currentPage });

      if (result.videos && result.videos.length > 0) {
        // Fetch detail files for each video
        for (let i = 0; i < result.videos.length; i++) {
          const video = result.videos[i];
          try {
            console.log(`  Fetching details for video ${i + 1}/${result.videos.length}: ${video.title}`);
            const details = await xvideos.videos.details({ url: video.url });
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
