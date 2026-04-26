const xvideos = module.exports = require('./lib');

(async () => {

  //const fresh = await xvideos.videos.fresh({ page: 1 });


// const bestList = await xvideos.videos.best({ year: '2026', month: '02', page: 1 });

// console.log(bestList);


// Retrieve detailed information about a specific video using its URL
const details = await xvideos.videos.details({ url: 'https://www.xvideos.com/video.itbkuvoe99e/_' });

// Log detailed information about the video
console.log(details);







})();