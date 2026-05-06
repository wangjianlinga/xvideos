const { parentPort } = require('worker_threads');
const xvideos = require('./lib');

async function fetchDetails(url) {
  return xvideos.videos.details({ url });
}

async function run() {
  while (true) {
    parentPort.postMessage({ type: 'ready' });

    const task = await new Promise((resolve) => {
      const handler = (msg) => {
        if (msg.type === 'url' || msg.type === 'exit') {
          parentPort.off('message', handler);
          resolve(msg);
        }
      };
      parentPort.on('message', handler);
    });

    if (task.type === 'exit') {
      break;
    }

    const { url } = task;
    try {
      const details = await fetchDetails(url);
      parentPort.postMessage({ type: 'success', url, details });
    } catch (error) {
      parentPort.postMessage({ type: 'error', url, error: error.message });
    }
  }
}

run().catch((err) => {
  parentPort.postMessage({ type: 'fatal', error: err.message });
  process.exit(1);
});
