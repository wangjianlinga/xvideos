const fs = require('fs');
const path = require('path');
const { saveDetail, saveDetails, getStats } = require('./lib/detail-db');

function printUsage() {
  console.log('Usage: node store-details.js <path-to-json-file>');
  console.log('');
  console.log('The JSON file must contain either:');
  console.log('  - A single detail object');
  console.log('  - An array of detail objects');
  console.log('');
  console.log('Expected structure example:');
  console.log(`
{
  "title": "Example Video",
  "url": "https://example.com/video123",
  "duration": "10:23",
  "image": "https://example.com/thumb.jpg",
  "views": "1.2M",
  "videoType": "mp4",
  "videoWidth": 1920,
  "videoHeight": 1080,
  "files": {
    "low": "https://example.com/low.mp4",
    "high": "https://example.com/high.mp4",
    "HLS": "https://example.com/hls.m3u8",
    "thumb": "https://example.com/thumb.jpg",
    "thumb69": "https://example.com/thumb69.jpg",
    "thumbSlide": "https://example.com/thumbSlide.jpg",
    "thumbSlideBig": "https://example.com/thumbSlideBig.jpg"
  }
}
  `);
}

function run() {
  const inputPath = process.argv[2];

  // Demo mode: store an empty-structure sample when no file is given
  if (!inputPath) {
    console.log('No JSON file provided. Running in demo mode...');
    console.log('(Pass a JSON file path to store your own data)\n');

    const demoDetails = {
      title: '',
      url: 'https://demo.example.com/video-sample',
      duration: '',
      image: '',
      views: '',
      videoType: undefined,
      videoWidth: undefined,
      videoHeight: undefined,
      files: {
        low: '',
        high: '',
        HLS: '',
        thumb: '',
        thumb69: '',
        thumbSlide: '',
        thumbSlideBig: ''
      }
    };

    const result = saveDetail(demoDetails);
    console.log('Demo record stored successfully.');
    console.log('Changes:', result.changes);
    console.log('Last inserted row id:', result.lastInsertRowid);
    console.log('\nCurrent DB stats:', getStats());
    return;
  }

  const resolvedPath = path.resolve(inputPath);
  if (!fs.existsSync(resolvedPath)) {
    console.error(`Error: File not found: ${resolvedPath}`);
    printUsage();
    process.exit(1);
  }

  let raw;
  try {
    raw = fs.readFileSync(resolvedPath, 'utf-8');
  } catch (err) {
    console.error('Error reading file:', err.message);
    process.exit(1);
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch (err) {
    console.error('Error parsing JSON:', err.message);
    process.exit(1);
  }

  let count;
  if (Array.isArray(data)) {
    count = saveDetails(data);
    console.log(`Stored ${count} detail records from array.`);
  } else if (typeof data === 'object' && data !== null) {
    const result = saveDetail(data);
    count = result.changes ? 1 : 0;
    console.log(`Stored 1 detail record.`);
  } else {
    console.error('Error: JSON must be an object or an array of objects.');
    process.exit(1);
  }

  console.log('\nCurrent DB stats:', getStats());
}

run();
