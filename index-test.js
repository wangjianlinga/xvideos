const xvideos = module.exports = require('./lib');

(async () => {
  const fresh = await xvideos.videos.fresh({ page: 1 });
  // Log details of the retrieved videos
  console.log(fresh.videos);
})();