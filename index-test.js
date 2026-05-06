const xvideos = module.exports = require('./lib');

(async () => {

  //const fresh = await xvideos.videos.fresh({ page: 1 });


  // const bestList = await xvideos.videos.best({ year: '2026', month: '02', page: 1 });

  // console.log(bestList);


  const details = await xvideos.videos.details({ url: 'https://www.xvideos.com/video36638661/chaturbate_lulacum69_30-05-2018' });

 // Log detailed information about the video
 console.log(details); // Detailed video object with properties like title, duration, image, videoType, views, files




})();