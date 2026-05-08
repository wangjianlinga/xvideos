const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const configPath = path.join(__dirname, '..', 'config.json');
const config = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : {};
const DB_NAME = config.db_name || 'videos.db';

const DB_PATH = path.join(DATA_DIR, DB_NAME);
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
    favorite INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    downloaded INTEGER DEFAULT 0,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_videos_page ON videos(page_number);
  CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
  CREATE INDEX IF NOT EXISTS idx_videos_favorite ON videos(favorite);
  CREATE INDEX IF NOT EXISTS idx_videos_deleted ON videos(is_deleted);
  CREATE INDEX IF NOT EXISTS idx_videos_downloaded ON videos(downloaded);
`);

// Migrate: add missing columns if they don't exist
const tableInfo = db.prepare("PRAGMA table_info(videos)").all();
const hasSource = tableInfo.some(col => col.name === 'source');
if (!hasSource) {
  db.exec(`ALTER TABLE videos ADD COLUMN source TEXT`);
}
const hasDownloaded = tableInfo.some(col => col.name === 'downloaded');
if (!hasDownloaded) {
  db.exec(`ALTER TABLE videos ADD COLUMN downloaded INTEGER DEFAULT 0`);
}

const insertVideo = db.prepare(`
  INSERT OR IGNORE INTO videos (video_path, url, title, duration, profile_name, profile_url, views, page_number, source)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

function saveVideos(videos, pageNumber, source) {
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
        source || null
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

function filterVideosByProfile(profile, page = 1, limit = 20) {
  const offset = (page - 1) * limit;
  const profileTerm = `%${profile}%`;
  const rows = db.prepare('SELECT * FROM videos WHERE profile_name LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?').all(profileTerm, limit, offset);
  const countRow = db.prepare('SELECT COUNT(*) as total FROM videos WHERE profile_name LIKE ?').get(profileTerm);
  return {
    videos: rows,
    total: countRow.total,
    page,
    pages: Math.ceil(countRow.total / limit)
  };
}

module.exports = {
  saveVideos,
  getVideos,
  getStats,
  filterVideosByProfile,
  db
};
