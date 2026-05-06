const { Worker } = require('worker_threads');
const os = require('os');
const path = require('path');
const { db: sourceDb } = require('./lib/db');
const { saveDetail, db: targetDb } = require('./lib/detail-db');

const WORKER_COUNT = process.argv[2] ? parseInt(process.argv[2], 10) : Math.min(os.cpus().length, 4);
const ONLY_NEW = process.argv.includes('--all') ? false : true;

const workerPath = path.resolve(__dirname, 'crawler-detail-worker.js');

function getPendingUrls() {
  let urls;
  try {
    urls = sourceDb.prepare('SELECT url FROM videos').all().map(r => r.url);
  } catch (err) {
    console.error('Failed to read videos.db:', err.message);
    process.exit(1);
  }

  if (!ONLY_NEW) {
    return urls;
  }

  const existingRows = targetDb.prepare('SELECT url FROM video_details').all();
  const existing = new Set(existingRows.map(r => r.url));
  const pending = urls.filter(url => !existing.has(url));
  console.log(`Found ${urls.length} total URLs, ${pending.length} pending (skipped ${existing.size} existing).`);
  return pending;
}

async function run() {
  const urls = getPendingUrls();
  if (urls.length === 0) {
    console.log('No URLs to process.');
    process.exit(0);
  }

  console.log(`Starting detail crawler with ${WORKER_COUNT} worker(s)...`);
  console.log(`Total tasks: ${urls.length}`);
  console.log(`Mode: ${ONLY_NEW ? 'resume (skip existing)' : 're-crawl all'}`);
  console.log('Press Ctrl+C to stop gracefully.\n');

  const queue = [...urls];
  let completed = 0;
  let failed = 0;
  let saved = 0;
  const startTime = Date.now();
  let shuttingDown = false;

  const workers = [];
  const workerStates = new Map(); // worker -> 'idle' | 'busy'

  function printProgress() {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const rate = completed > 0 ? (completed / (Date.now() - startTime) * 1000).toFixed(2) : '0.00';
    process.stdout.write(`\r[${elapsed}s] Progress: ${completed}/${urls.length} | Saved: ${saved} | Failed: ${failed} | Rate: ${rate}/s | Queue: ${queue.length} `);
  }

  function assignWork(worker) {
    if (shuttingDown || queue.length === 0) {
      worker.postMessage({ type: 'exit' });
      workerStates.set(worker, 'exiting');
      return;
    }
    const url = queue.shift();
    workerStates.set(worker, 'busy');
    worker.postMessage({ type: 'url', url });
  }

  function shutdown() {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log('\n\nShutting down gracefully...');
    for (const worker of workers) {
      if (workerStates.get(worker) === 'idle') {
        worker.postMessage({ type: 'exit' });
        workerStates.set(worker, 'exiting');
      }
    }
  }

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  const allFinished = new Promise((resolve) => {
    let activeWorkers = 0;

    for (let i = 0; i < WORKER_COUNT; i++) {
      const worker = new Worker(workerPath);
      workers.push(worker);
      workerStates.set(worker, 'idle');
      activeWorkers++;

      worker.on('message', (msg) => {
        if (msg.type === 'ready') {
          workerStates.set(worker, 'idle');
          assignWork(worker);
          return;
        }

        if (msg.type === 'success') {
          try {
            saveDetail(msg.details);
            saved++;
          } catch (dbErr) {
            console.error(`\nDB save failed for ${msg.url}:`, dbErr.message);
          }
          completed++;
        } else if (msg.type === 'error') {
          failed++;
          completed++;
          // Keep error log minimal to avoid spam; uncomment below for verbose
          // console.error(`\nFailed ${msg.url}: ${msg.error}`);
        } else if (msg.type === 'fatal') {
          console.error(`\nWorker fatal error: ${msg.error}`);
        }

        printProgress();

        if (workerStates.get(worker) !== 'exiting') {
          assignWork(worker);
        }
      });

      worker.on('error', (err) => {
        console.error('\nWorker crashed:', err.message);
        activeWorkers--;
        if (activeWorkers <= 0) resolve();
      });

      worker.on('exit', (code) => {
        if (code !== 0 && code !== null) {
          console.error(`\nWorker stopped with exit code ${code}`);
        }
        activeWorkers--;
        if (activeWorkers <= 0) {
          resolve();
        }
      });
    }
  });

  await allFinished;

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\n\nDone in ${elapsed}s.`);
  console.log(`Completed: ${completed} | Saved: ${saved} | Failed: ${failed}`);
  process.exit(0);
}

run().catch((err) => {
  console.error('Crawler failed:', err);
  process.exit(1);
});
