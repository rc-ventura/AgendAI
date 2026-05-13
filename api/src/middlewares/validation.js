/**
 * Shared input validation helpers.
 * Each returns true when the value is valid.
 */

function isValidEmail(email) {
  return typeof email === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function isValidDate(dateStr) {
  if (typeof dateStr !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return false;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return false;
  // Reject calendar dates that JS silently auto-corrects (e.g. 2026-02-30 → 2026-03-02).
  // Input is parsed as UTC midnight, so comparing the UTC date string is consistent.
  return d.toISOString().slice(0, 10) === dateStr;
}

function isPositiveInteger(value) {
  const n = Number(value);
  return Number.isInteger(n) && n > 0;
}

module.exports = { isValidEmail, isValidDate, isPositiveInteger };
