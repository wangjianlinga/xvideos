const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const DB_PATH = path.join(DATA_DIR, 'videos-detail.db');
const db = new Database(DB_PATH);

db.exec(`
  CREATE TABLE IF NOT EXISTS video_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    duration TEXT,
    image TEXT,
    views TEXT,
    videoType TEXT,
    videoWidth INTEGER,
    videoHeight INTEGER,
    files_low TEXT,
    files_high TEXT,
    files_HLS TEXT,
    files_thumb TEXT,
    files_thumb69 TEXT,
    files_thumbSlide TEXT,
    files_thumbSlideBig TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_video_details_url ON video_details(url);
  CREATE INDEX IF NOT EXISTS idx_video_details_created ON video_details(created_at);
`);

const insertDetail = db.prepare(`
  INSERT INTO video_details (
    url, title, duration, image, views,
    videoType, videoWidth, videoHeight,
    files_low, files_high, files_HLS,
    files_thumb, files_thumb69, files_thumbSlide, files_thumbSlideBig
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT(url) DO UPDATE SET
    title = excluded.title,
    duration = excluded.duration,
    image = excluded.image,
    views = excluded.views,
    videoType = excluded.videoType,
    videoWidth = excluded.videoWidth,
    videoHeight = excluded.videoHeight,
    files_low = excluded.files_low,
    files_high = excluded.files_high,
    files_HLS = excluded.files_HLS,
    files_thumb = excluded.files_thumb,
    files_thumb69 = excluded.files_thumb69,
    files_thumbSlide = excluded.files_thumbSlide,
    files_thumbSlideBig = excluded.files_thumbSlideBig,
    updated_at = CURRENT_TIMESTAMP
`);

function saveDetail(details) {
  const files = details.files || {};
  const result = insertDetail.run(
    details.url,
    details.title || null,
    details.duration || null,
    details.image || null,
    details.views || null,
    details.videoType || null,
       details.videoWidth || null,
    details.videoHeight || null,
    files.low || null,
    files.high || null,
    files.HLS || null,
    files.thumb || null,
    files.thumb69 || null,
    files.thumbSlide || null,
    files.thumbSlideBig || null
  );
  return result;
}

function saveDetails(detailsList) {
  const insertMany = db.transaction((list) => {
    for (const details of list) {
      saveDetail(details);
    }
  });
  insertMany(detailsList);
  return detailsList.length;
}

function getDetail(url) {
  return db.prepare('SELECT * FROM video_details WHERE url = ?').get(url);
}

function getDetails(page = 1, limit = 20) {
  const offset = (page - 1) * limit;
  const rows = db.prepare('SELECT * FROM video_details ORDER BY created_at DESC LIMIT ? OFFSET ?').all(limit, offset);
  const countRow = db.prepare('SELECT COUNT(*) as total FROM video_details').get();
  return {
    details: rows,
    total: countRow.total,
    page,
    pages: Math.ceil(countRow.total / limit)
  };
}

function getStats() {
  return db.prepare('SELECT COUNT(*) as total, MAX(updated_at) as last_update FROM video_details').get();
}

module.exports = {
  saveDetail,
  saveDetails,
  getDetail,
  getDetails,
  getStats,
  db
};
