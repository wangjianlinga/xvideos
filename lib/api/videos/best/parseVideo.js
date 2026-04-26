const base = require('../../base');

const parseVideo = ($, video) => {
  const $video = $(video);

  const title = $video.find('.title a').text();
  const path = $video.find('.thumb-link').attr('href');
  const url = `${base.BASE_URL}${path}`;
  const views = $video.find('.video-metadata .views-count').text();
  const duration = $video.find('.video-metadata .duration').text();
  const profileElement = $video.find('.video-metadata .name');
  const profile = {
    name: profileElement.text(),
    url: `${base.BASE_URL}${profileElement.attr('href')}`,
  };

  return {
    url,
    path,
    title,
    duration,
    profile,
    views,
  };
};

module.exports = parseVideo;
