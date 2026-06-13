'use strict';
const pRetry = require('p-retry');
const retry = pRetry.default;
const { AbortError } = pRetry;

/**
 * Initialize database schema and seed with retry logic.
 * Retries on transient Postgres startup delays (ECONNREFUSED / ENOTFOUND).
 * Aborts immediately on auth errors (not retryable).
 */
async function initializeWithRetry(pool, initSchema, seed) {
  await retry(
    async () => {
      await initSchema(pool);
      await seed(pool);
    },
    {
      retries: 4,
      minTimeout: 1000,
      maxTimeout: 5000,
      factor: 2,
      onFailedAttempt: (err) => {
        if (err.code === 'EAUTH' || err.message?.includes('password')) {
          throw new AbortError(err);
        }
        console.warn(`[db/init] DB not ready (attempt ${err.attemptNumber}): ${err.message}`);
      },
    }
  );
}

module.exports = { initializeWithRetry };
