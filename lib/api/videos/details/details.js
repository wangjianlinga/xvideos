const cheerio = require('cheerio');
const puppeteer = require('puppeteer');

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const details = async ({ url, puppeteerConfig } = {}) => {
  if (!url) {
    throw new Error('URL is required');
  }

  const MAX_RETRIES = 3;
  let lastError;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    let browser;
    try {
      browser = await puppeteer.launch({
        headless: 'new',
        ...puppeteerConfig,
      });
      const page = await browser.newPage();

      await page.setUserAgent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      );

      await page.setViewport({ width: 1366, height: 768 });

      // Block images, CSS, fonts to speed up loading
      await page.setRequestInterception(true);
      page.on('request', (req) => {
        const resourceType = req.resourceType();
        if (resourceType === 'image' || resourceType === 'stylesheet' || resourceType === 'font' || resourceType === 'media') {
          req.abort();
        } else {
          req.continue();
        }
      });

      await page.goto(url, {
        waitUntil: 'networkidle2',
        timeout: 60000,
      });

      const html = await page.content();
      const $ = cheerio.load(html);

      const title = $('meta[property="og:title"]').attr('content');
      const duration = $('meta[property="og:duration"]').attr('content');
      const image = $('meta[property="og:image"]').attr('content');
      const videoType = $('meta[property="og:video:type"]').attr('content');
      const videoWidth = $('meta[property="og:video:width"]').attr('content');
      const videoHeight = $('meta[property="og:video:height"]').attr('content');
      const views = $('#nb-views-number').text();
      const videoScript = $('#video-player-bg > script:nth-child(6)').html();

      const files = {
        low: (videoScript.match("html5player.setVideoUrlLow\\('(.*?)'\\);") || [])[1],
        high: (videoScript.match("html5player.setVideoUrlHigh\\('(.*?)'\\);") || [])[1],
        HLS: (videoScript.match("html5player.setVideoHLS\\('(.*?)'\\);") || [])[1],
        thumb: (videoScript.match("html5player.setThumbUrl\\('(.*?)'\\);") || [])[1],
        thumb69: (videoScript.match("html5player.setThumbUrl169\\('(.*?)'\\);") || [])[1],
        thumbSlide: (videoScript.match("html5player.setThumbSlide\\('(.*?)'\\);") || [])[1],
        thumbSlideBig: (videoScript.match("html5player.setThumbSlideBig\\('(.*?)'\\);") || [])[1],
      };

      return {
        title,
        url,
        duration,
        image,
        views,
        videoType,
        videoWidth,
        videoHeight,
        files,
      };
    } catch (error) {
      lastError = error;
      console.warn(`Puppeteer attempt ${attempt}/${MAX_RETRIES} failed: ${error.message}`);
      if (attempt < MAX_RETRIES) {
        await sleep(2000 * attempt);
      }
    } finally {
      if (browser) {
        try {
          await browser.close();
        } catch (e) {
          // ignore close errors
        }
      }
    }
  }

  throw new Error(`All ${MAX_RETRIES} attempts failed. Last error: ${lastError.message}`);
};

module.exports = details;
