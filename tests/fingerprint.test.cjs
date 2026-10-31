const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const viewer = require(fs.existsSync(path.join(root, 'web/fingerprint.js')) ? '../web/fingerprint.js' : '../assets/market/fingerprint.js');
const keys = ['sp500', 'nasdaq100', 'dow', 'vix', 'bitcoin', 'gold', 'tnx', 'dxy', 'wti'];
const row = { date: '2026-10-30', source: 'Yahoo Finance' };
for (const key of keys) Object.assign(row, key === 'bitcoin'
  ? { bitcoin_open: '100', bitcoin_current: '101', bitcoin_change: '1', bitcoin_change_pct: '1' }
  : Object.fromEntries(['previous_close', 'open', 'gap', 'gap_pct'].map((suffix, i) => [`${key}_${suffix}`, ['100', '101', '1', '1'][i]])));
const csv = (records) => `${Object.keys(row).join(',')}\n${records.map((record) => Object.keys(row).map((key) => `"${String(record[key]).replaceAll('"', '""')}"`).join(',')).join('\n')}`;

test('CSV supports quoted sources, all nine indicators and sorted dates', () => {
  const records = viewer.parseCsv(csv([row, { ...row, date: '2026-10-29', source: 'Yahoo, "Finance"' }]));
  assert.equal(records[0].date, '2026-10-29');
  assert.equal(records[0].source, 'Yahoo, "Finance"');
  assert.equal(records[1].gold_gap_pct, '1');
});
test('invalid dates, duplicate dates and missing nine-indicator fields fail visibly', () => {
  assert.throws(() => viewer.parseCsv(csv([{ ...row, date: '2026-02-30' }])));
  assert.throws(() => viewer.parseCsv(csv([row, row])));
  assert.throws(() => viewer.parseCsv(csv([row]).replace('gold_gap_pct', 'other')));
});
test('migrated unavailable values remain unavailable', () => {
  const result = viewer.parseCsv(csv([{ ...row, bitcoin_change_pct: 'NA' }]))[0];
  assert.equal(viewer.measurement(result, 'bitcoin').adjusted, 'NA');
  assert.throws(() => viewer.validateSvgValues(result.date, Array(9).fill(1), result));
});
test('raw values preserve signs while only VIX and DXY positions/colors reverse', () => {
  for (const key of keys) {
    const item = viewer.measurement(row, key);
    assert.equal(item.raw, '1');
    assert.equal(item.adjusted, ['vix', 'dxy'].includes(key) ? -1 : 1);
  }
  assert.equal(viewer.measurement(row, 'bitcoin').baselineLabel, '00:00 UTC open');
  assert.equal(viewer.measurement(row, 'tnx').currentLabel, 'Daily open');
});
test('SVG must match the selected date and exact source values, including Bitcoin', () => {
  viewer.validateSvgValues(row.date, Array(9).fill(1), row);
  assert.throws(() => viewer.validateSvgValues('2026-10-29', Array(9).fill(1), row));
  const values = Array(9).fill(1); values[4] = 1.1;
  assert.throws(() => viewer.validateSvgValues(row.date, values, row));
});
