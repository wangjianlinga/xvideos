const xvideos = require('../lib');
const Database = require('better-sqlite3');
const path = require('path');

// 旧数据库（读取 url）
const oldDbPath = path.join(__dirname, 'videos.db');
const oldDb = new Database(oldDbPath);

// 新数据库（保存详情）
const newDbPath = path.join(__dirname, 'video_details.db');
const newDb = new Database(newDbPath);

// 创建新表
newDb.exec(`
  CREATE TABLE IF NOT EXISTS video_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    duration TEXT,
    image TEXT,
    views TEXT,
    videoType TEXT,
    videoWidth TEXT,
    videoHeight TEXT,
    file_low TEXT,
    file_high TEXT,
    file_HLS TEXT,
    file_thumb TEXT,
    file_thumb69 TEXT,
    file_thumbSlide TEXT,
    file_thumbSlideBig TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
`);

const insertStmt = newDb.prepare(`
  INSERT INTO video_details (
    url, title, duration, image, views,
    videoType, videoWidth, videoHeight,
    file_low, file_high, file_HLS,
    file_thumb, file_thumb69, file_thumbSlide, file_thumbSlideBig
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

async function main() {
  // 读取所有 url（去重）
  const rows = oldDb.prepare('SELECT DISTINCT url FROM videos').all();
  console.log(`共读取到 ${rows.length} 个 URL`);

  for (const row of rows) {
    const url = row.url;

    let detail;
    try {
      // 调用接口获取详情
      detail = await xvideos.videos.details({ url });
    } catch (err) {
      // 接口不通时使用默认空结构
      console.warn(`接口调用失败 [${url}]，使用默认值`);
      detail = {
        title: '',
        url: url,
        duration: '',
        image: '',
        views: '',
        videoType: '',
        videoWidth: '',
        videoHeight: '',
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
    }

    insertStmt.run(
      detail.url || '',
      detail.title || '',
      detail.duration || '',
      detail.image || '',
      detail.views || '',
      detail.videoType || '',
      detail.videoWidth || '',
      detail.videoHeight || '',
      detail.files?.low || '',
      detail.files?.high || '',
      detail.files?.HLS || '',
      detail.files?.thumb || '',
      detail.files?.thumb69 || '',
      detail.files?.thumbSlide || '',
      detail.files?.thumbSlideBig || ''
    );

    console.log(`已保存: ${url}`);
  }

  console.log('全部处理完成');
  oldDb.close();
  newDb.close();
}

main().catch(console.error);
