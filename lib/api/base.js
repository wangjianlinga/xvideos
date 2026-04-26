const axios = require('axios');

const BASE_URL = "https://www.xvideos.com";
const DEFAULT_TIMEOUT = 30000;
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const createRequest = (options = {}) => {
  const instance = axios.create({
    baseURL: BASE_URL,
    timeout: DEFAULT_TIMEOUT,
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.5',
      'Accept-Encoding': 'gzip, deflate, br',
      'DNT': '1',
      'Connection': 'keep-alive',
    },
    ...options,
  });

  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      const config = error.config;
      if (!config) return Promise.reject(error);

      config._retryCount = config._retryCount || 0;

      const isNetworkError = !error.response;
      const isTimeout = error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT';
      const is5xx = error.response && error.response.status >= 500;

      if ((isNetworkError || isTimeout || is5xx) && config._retryCount < MAX_RETRIES) {
        config._retryCount += 1;
        console.warn(`Request failed (${error.message}), retrying ${config._retryCount}/${MAX_RETRIES}...`);
        await sleep(RETRY_DELAY * config._retryCount);
        return instance(config);
      }

      return Promise.reject(error);
    }
  );

  return instance;
};

const base = {
  BASE_URL,
  createRequest,
};

module.exports = base;
