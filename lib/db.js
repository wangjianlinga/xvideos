const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const DB_PATH = path.join(DATA_DIR, 'videos.db');
const db = new Database(DB_PATH);

db.exec(`
  CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_path TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    duration TEXT,
    profile_name TEXT,
    profile_url TEXT,
    views TEXT,
    page_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_videos_page ON videos(page_number);
  CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
`);

// Add file columns (idempotent — ignore if already exist)
const fileColumns = ['file_high', 'file_thumb', 'file_thumb69', 'file_thumb_slide', 'file_thumb_slide_big'];
for (const col of fileColumns) {
  try {
    db.exec(`ALTER TABLE videos ADD COLUMN ${col} TEXT`);
  } catch (e) {
    // Column already exists — ignore
  }
}

const insertVideo = db.prepare(`
  INSERT INTO videos (video_path, url, title, duration, profile_name, profile_url, views, page_number,
                       file_high, file_thumb, file_thumb69, file_thumb_slide, file_thumb_slide_big)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT(video_path) DO UPDATE SET
    file_high = excluded.file_high,
    file_thumb = excluded.file_thumb,
    file_thumb69 = excluded.file_thumb69,
    file_thumb_slide = excluded.file_thumb_slide,
    file_thumb_slide_big = excluded.file_thumb_slide_big
`);

function saveVideos(videos, pageNumber) {
  const insertMany = db.transaction((videoList) => {
    for (const video of videoList) {
      insertVideo.run(
        video.path,
        video.url,
        video.title || null,
        video.duration || null,
        video.profile?.name || null,
        video.profile?.url || null,
        video.views || null,
        pageNumber,
        video.files?.high || null,
        video.files?.thumb || null,
        video.files?.thumb69 || null,
        video.files?.thumbSlide || null,
        video.files?.thumbSlideBig || null
      );
    }
  });
  insertMany(videos);
  return videos.length;
}

function getVideos(page = 1, limit = 20) {
  const offset = (page - 1) * limit;
  const rows = db.prepare('SELECT * FROM videos ORDER BY created_at DESC LIMIT ? OFFSET ?').all(limit, offset);
  const countRow = db.prepare('SELECT COUNT(*) as total FROM videos').get();
  return {
    videos: rows,
    total: countRow.total,
    page,
    pages: Math.ceil(countRow.total / limit)
  };
}

function getStats() {
  return db.prepare('SELECT COUNT(*) as total, MAX(created_at) as last_crawl FROM videos').get();
}

module.exports = {
  saveVideos,
  getVideos,
  getStats,
  db
};
