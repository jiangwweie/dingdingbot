import assert from 'node:assert/strict';
import { evaluateSessionAuth } from './verify_k_line_live.mjs';

console.log('================================================================');
console.log('Running Live Script Auth Verification Branch Suite');
console.log('================================================================\n');

let passCount = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`  ✗ FAIL: ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

// ---------------------------------------------------------------------------
// Success Branch
// ---------------------------------------------------------------------------
test('evaluateSessionAuth: Success requires HTTP 200, authenticated === true, and authenticated UI', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { authenticated: true } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, true);
  assert.equal(result.reason, null);
});

// ---------------------------------------------------------------------------
// Negative Branches: Network & HTTP Status
// ---------------------------------------------------------------------------
test('evaluateSessionAuth: Rejects when no response was received (request observed only)', () => {
  const result = evaluateSessionAuth(null, { isLoginVisible: false, isHeaderPresent: true });
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('No response received'));
});

test('evaluateSessionAuth: Rejects HTTP 401 Unauthorized', () => {
  const result = evaluateSessionAuth(
    { status: 401, body: { error: 'unauthorized' } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('HTTP status is 401'));
});

test('evaluateSessionAuth: Rejects HTTP 403 Forbidden', () => {
  const result = evaluateSessionAuth(
    { status: 403, body: { error: 'forbidden' } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('HTTP status is 403'));
});

test('evaluateSessionAuth: Rejects HTTP 500 / 5xx Server Error', () => {
  const result = evaluateSessionAuth(
    { status: 500, body: { error: 'server_error' } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('HTTP status is 500'));
});

// ---------------------------------------------------------------------------
// Negative Branches: Body & Field Type
// ---------------------------------------------------------------------------
test('evaluateSessionAuth: Rejects when body is null or non-JSON', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: null },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('not valid JSON'));
});

test('evaluateSessionAuth: Rejects when authenticated is boolean false', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { authenticated: false } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('expected boolean true'));
});

test('evaluateSessionAuth: Rejects when authenticated is string "true"', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { authenticated: 'true' } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('type string'));
});

test('evaluateSessionAuth: Rejects when authenticated is number 1', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { authenticated: 1 } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('type number'));
});

test('evaluateSessionAuth: Rejects when authenticated field is missing entirely', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { user: 'admin' } },
    { isLoginVisible: false, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('type undefined'));
});

// ---------------------------------------------------------------------------
// Negative Branches: UI State
// ---------------------------------------------------------------------------
test('evaluateSessionAuth: Rejects if login form remains visible in viewport', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { authenticated: true } },
    { isLoginVisible: true, isHeaderPresent: true }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('Login form is still visible'));
});

test('evaluateSessionAuth: Rejects if authenticated header is absent', () => {
  const result = evaluateSessionAuth(
    { status: 200, body: { authenticated: true } },
    { isLoginVisible: false, isHeaderPresent: false }
  );
  assert.equal(result.ok, false);
  assert.ok(result.reason.includes('header / navigation bar is not rendered'));
});

console.log('\n================================================================');
console.log(`Live Auth Verification Summary: ${passCount} Passed, 0 Failed`);
console.log('================================================================\n');
