const fs = require('fs');
const path = require('path');
const axios = require('axios');

const VIDEO_URL = process.argv[2];
if (!VIDEO_URL) {
  console.error('Usage: node download-video.js <video-url>');
  process.exit(1);
}

let fileName;
try {
  fileName = path.basename(new URL(VIDEO_URL).pathname) || 'video.mp4';
} catch {
  fileName = 'video.mp4';
}

const outputPath = path.join(__dirname, 'data', fileName);
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

(async () => {
  try {
    console.log('Downloading...');
    console.log('URL:', VIDEO_URL);
    console.log('Save to:', outputPath);

    const response = await axios({
      method: 'GET',
      url: VIDEO_URL,
      responseType: 'stream',
      timeout: 120000,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.xv.com/',
      },
      maxRedirects: 5,
    });

    const totalLength = response.headers['content-length'];
    const writer = fs.createWriteStream(outputPath);
    let downloaded = 0;
    let lastLogged = 0;

    response.data.on('data', (chunk) => {
      downloaded += chunk.length;
      if (totalLength) {
        const percent = Math.round((downloaded / totalLength) * 100);
        if (percent >= lastLogged + 10) {
          console.log(`  Progress: ${percent}%`);
          lastLogged = percent;
        }
      }
    });

    response.data.pipe(writer);

    await new Promise((resolve, reject) => {
      writer.on('finish', resolve);
      writer.on('error', reject);
    });

    const stats = fs.statSync(outputPath);
    console.log(`Done! File size: ${(stats.size / 1024 / 1024).toFixed(2)} MB`);
    console.log(`Saved as: ${outputPath}`);
  } catch (err) {
    console.error('Download failed:', err.message);
    if (fs.existsSync(outputPath)) {
      fs.unlinkSync(outputPath);
    }
    process.exit(1);
  }
})();
