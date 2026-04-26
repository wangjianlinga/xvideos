const xvideos = module.exports = require('./lib');

(async () => {

  //const fresh = await xvideos.videos.fresh({ page: 1 });


const bestList = await xvideos.videos.best({ year: '2026', month: '02', page: 1 });

  console.log(bestList);




})();