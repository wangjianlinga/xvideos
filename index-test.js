const xvideos = module.exports = require('./lib');

(async () => {

   const fresh = await xvideos.videos.fresh({ page: 1 });


  // const bestList = await xvideos.videos.best({ year: '2026', month: '02', page: 1 });

  // console.log(bestList);


  const videos = await xvideos.videos.search({ k: '抖音', page: 5 });
   console.log(videos);


})();
