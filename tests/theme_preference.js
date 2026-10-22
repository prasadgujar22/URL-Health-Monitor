// Run with `node tests/theme_preference.js`; no browser dependencies required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const script = fs.readFileSync('app/static/theme.js', 'utf8');

function load({saved = null, dark = false, storageThrows = false} = {}) {
  const listeners = {};
  const values = new Map(saved === null ? [] : [['url-health-theme', saved]]);
  const root = {dataset: {}, style: {}};
  const selector = {value: '', addEventListener(type, callback) { listeners[type] = callback; }};
  const media = {matches: dark, addEventListener(type, callback) { listeners.media = callback; }};
  const localStorage = {
    getItem(key) { if (storageThrows) throw Error('blocked'); return values.get(key) ?? null; },
    setItem(key, value) { if (storageThrows) throw Error('blocked'); values.set(key, value); },
  };
  const document = {
    documentElement: root,
    getElementById() { return selector; },
    addEventListener(type, callback) { listeners[type] = callback; },
  };
  vm.runInNewContext(script, {document, window: {matchMedia: () => media, localStorage}});
  const beforeDomReady = root.dataset.theme;
  listeners.DOMContentLoaded();
  return {
    root, selector, media, values, beforeDomReady,
    change(value) { selector.value = value; listeners.change(); },
    osChange(isDark) { media.matches = isDark; listeners.media(); },
  };
}

const system = load({dark: true});
assert.equal(system.beforeDomReady, 'dark', 'theme is applied before DOM ready');
assert.equal(system.selector.value, 'system', 'missing preference defaults to System');
system.osChange(false);
assert.equal(system.root.dataset.theme, 'light');
system.change('dark');
assert.equal(system.values.get('url-health-theme'), 'dark');
system.osChange(false);
assert.equal(system.root.dataset.theme, 'dark', 'explicit override ignores OS changes');
assert.equal(load({saved: system.values.get('url-health-theme')}).beforeDomReady, 'dark', 'reload keeps saved preference');
system.change('system');
system.osChange(true);
assert.equal(system.root.dataset.theme, 'dark', 'System resumes following OS');

const invalid = load({saved: 'sepia', dark: true});
assert.equal(invalid.selector.value, 'system');
assert.equal(invalid.beforeDomReady, 'dark');

const restricted = load({dark: true, storageThrows: true});
restricted.change('light');
assert.equal(restricted.root.dataset.theme, 'light', 'storage failure does not prevent theme changes');

console.log('theme preference, prepaint, System, override, reload, invalid value, and storage regression passed');
