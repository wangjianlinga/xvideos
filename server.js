const http = require('http');
const fs = require('fs');
const path = require('path');
const sqlite3 = require('better-sqlite3');
const url = require('url');

const PORT = 8000;
const STATIC_DIR = path.join(__dirname, 'api', 'static');
const DB_PATH = path.join(__dirname, 'data', 'videos.db');
const DETAILS_DB_PATH = path.join(__dirname, 'data', 'video_details.db');

function getDb() {
  return new sqlite3(DB_PATH);
}

function getDetailsDb() {
  if (!fs.existsSync(DETAILS_DB_PATH)) return null;
  return new sqlite3(DETAILS_DB_PATH);
}

function sendJson(res, data, status = 200) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': '*',
    'Access-Control-Allow-Headers': '*'
  });
  res.end(JSON.stringify(data));
}

function serveStatic(reqPath, res) {
  let filePath = path.join(STATIC_DIR, reqPath === '/' ? 'index.html' : reqPath);
  if (!fs.existsSync(filePath)) filePath = path.join(STATIC_DIR, 'index.html');

  const ext = path.extname(filePath);
  const mime = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml'
  }[ext] || 'application/octet-stream';

  res.writeHead(200, {
    'Content-Type': mime,
    'Access-Control-Allow-Origin': '*'
  });
  res.end(fs.readFileSync(filePath));
}

const server = http.createServer((req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': '*',
      'Access-Control-Allow-Headers': '*'
    });
    return res.end();
  }

  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;
  const params = parsed.query;

  if (pathname === '/api/stats') {
    const db = getDb();
    const row = db.prepare('SELECT COUNT(*) as total, MAX(created_at) as last_crawl FROM videos').get();
    db.close();

    let totalDetails = 0;
    const ddb = getDetailsDb();
    if (ddb) {
      const drow = ddb.prepare('SELECT COUNT(*) as total_details FROM video_details').get();
      totalDetails = drow.total_details;
      ddb.close();
    }

    return sendJson(res, { ...row, total_details: totalDetails });
  }

  if (pathname === '/api/videos') {
    const page = parseInt(params.page || '1', 10);
    const limit = Math.min(parseInt(params.limit || '20', 10), 100);
    const offset = (page - 1) * limit;
    const search = params.search || '';
    const db = getDb();

    let total, rows;
    if (search) {
      const term = `%${search}%`;
      total = db.prepare('SELECT COUNT(*) as total FROM videos WHERE title LIKE ?').get(term).total;
      rows = db.prepare('SELECT * FROM videos WHERE title LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?').all(term, limit, offset);
    } else {
      total = db.prepare('SELECT COUNT(*) as total FROM videos').get().total;
      rows = db.prepare('SELECT * FROM videos ORDER BY created_at DESC LIMIT ? OFFSET ?').all(limit, offset);
    }
    db.close();

    return sendJson(res, {
      videos: rows,
      pagination: { page, limit, total, pages: Math.ceil(total / limit) }
    });
  }

  if (pathname === '/api/video_details') {
    const page = parseInt(params.page || '1', 10);
    const limit = Math.min(parseInt(params.limit || '20', 10), 100);
    const offset = (page - 1) * limit;
    const search = params.search || '';
    const db = getDetailsDb();

    if (!db) {
      return sendJson(res, { videos: [], pagination: { page, limit, total: 0, pages: 0 } });
    }

    let total, rows;
    if (search) {
      const term = `%${search}%`;
      total = db.prepare('SELECT COUNT(*) as total FROM video_details WHERE title LIKE ?').get(term).total;
      rows = db.prepare('SELECT * FROM video_details WHERE title LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?').all(term, limit, offset);
    } else {
      total = db.prepare('SELECT COUNT(*) as total FROM video_details').get().total;
      rows = db.prepare('SELECT * FROM video_details ORDER BY created_at DESC LIMIT ? OFFSET ?').all(limit, offset);
    }
    db.close();

    return sendJson(res, {
      videos: rows,
      pagination: { page, limit, total, pages: Math.ceil(total / limit) }
    });
  }

  if (pathname.startsWith('/api/video_details/')) {
    const id = parseInt(pathname.split('/').pop(), 10);
    const db = getDetailsDb();
    if (!db) return sendJson(res, { error: 'Not found' }, 404);
    const row = db.prepare('SELECT * FROM video_details WHERE id = ?').get(id);
    db.close();
    if (!row) return sendJson(res, { error: 'Not found' }, 404);
    return sendJson(res, row);
  }

  if (pathname === '/api/crawl' || pathname === '/api/crawl/best' || pathname === '/api/video_details/fetch') {
    return sendJson(res, { success: true, message: 'Crawl triggered (run crawler manually)' });
  }

  return serveStatic(pathname, res);
});

server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
