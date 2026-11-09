const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeRanges, removeRange, restoredRanges } = require('../applications/class101-interview/underline.js');

test('overlapping and adjacent selections merge without changing the input', () => {
  const ranges = [[8, 12], [2, 5], [4, 8], [15, 18]];
  assert.deepEqual(mergeRanges(ranges, 20), [[2, 12], [15, 18]]);
  assert.deepEqual(ranges, [[8, 12], [2, 5], [4, 8], [15, 18]]);
});

test('invalid stored ranges are discarded', () => {
  assert.deepEqual(mergeRanges([null, {}, [0], ['0', 4], [-1, 3], [2, 2], [5, 3], [1, 30],
    [0.5, 2], [0, Infinity], [1, 4, 7], [2, 4]], 10), [[2, 4]]);
});

test('removing a selected middle splits a mark and preserves unrelated ranges', () => {
  assert.deepEqual(removeRange([[1, 10], [15, 20]], [4, 6]), [[1, 4], [6, 10], [15, 20]]);
  assert.deepEqual(removeRange([[1, 10], [15, 20]], [0, 17]), [[17, 20]]);
  assert.deepEqual(removeRange([[1, 10]], [10, 20]), [[1, 10]]);
  assert.deepEqual(removeRange([[1, 10]], [0, 11]), []);
});

test('restore requires exact content so edited answers never receive stale marks', () => {
  const entry = { text: '빠르게 배우고 깊게 몰입', ranges: [[0, 3], [4, 7]] };
  assert.deepEqual(restoredRanges(entry, entry.text), [[0, 3], [4, 7]]);
  assert.deepEqual(restoredRanges(entry, '새로운 답변'), []);
  assert.deepEqual(restoredRanges(null, entry.text), []);
  assert.deepEqual(restoredRanges({ text: entry.text, ranges: '<script>' }, entry.text), []);
});

test('offsets use DOM UTF-16 units including emoji and Korean text', () => {
  const text = '차 🍵 배우기';
  assert.deepEqual(restoredRanges({ text, ranges: [[2, 4], [5, text.length]] }, text), [[2, 4], [5, 8]]);
});
