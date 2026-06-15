'use strict';
const pRetry = require('p-retry');
const retry = pRetry.default;
const { AbortError } = pRetry;

// Postgres error codes that indicate a transient infrastructure problem.
const TRANSIENT_CODES = new Set(['ECONNRESET', 'ECONNREFUSED', 'ETIMEDOUT', '57P01', '08006', '08001']);

function isTransient(err) {
  return TRANSIENT_CODES.has(err.code) || /connection terminated|connection refused/i.test(err.message);
}

/**
 * Wrap a pg query call with retry logic for transient errors only.
 * Constraint violations (23xxx), auth errors, and other permanent failures
 * are NOT retried — they are re-thrown immediately via AbortError.
 */
async function withDbRetry(fn) {
  return retry(fn, {
    retries: 2,
    minTimeout: 200,
    maxTimeout: 2000,
    factor: 2,
    onFailedAttempt: (err) => {
      if (!isTransient(err)) {
        throw new AbortError(err);
      }
    },
  });
}

module.exports = { withDbRetry };
