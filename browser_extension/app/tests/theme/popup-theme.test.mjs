import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const app = new URL('../../', import.meta.url);
const html = readFileSync(new URL('popup.html', app), 'utf8');
const key = 'gd4bThemePreference';

function openPopup(cached) {
  const head = html.split('</head>')[0];
  assert.match(head, /<meta name="color-scheme" content="light dark"/);
  const script = head.match(/<script src="\/([^"/]+)"\s*><\/script>/);
  assert.ok(script, 'restore the canvas from a packaged, parser-blocking head script');
  const code = readFileSync(new URL(`public/${script[1]}`, app), 'utf8');
  const root = {dataset: {}};
  const meta = {content: 'light dark'};
  const cache = new Map([[key, cached]]);
  const window = {};
  let resolve;
  const promise = new Promise(done => {resolve = done;});
  const stored = {promise, resolve};
  let onChange;
  const writes = [];
  const local = {get: () => stored.promise, set: async value => {writes.push(value[key]);}};
  runInNewContext(code, {window, document: {documentElement: root, querySelector: () => meta},
    localStorage: {getItem: k => cache.get(k), setItem: (k,v) => cache.set(k,v), removeItem: k => cache.delete(k)},
    chrome: {storage: {local, onChanged: {addListener(fn) {onChange = fn;}}}}});
  return {root, meta, cache, store: window.popupTheme, stored, writes, onChange};
}

for (const mode of ['dark', 'light']) {
  test(`the canvas and initial React snapshot use saved ${mode} before extension storage resolves`, () => {
    const {root, meta, store} = openPopup(mode);
    assert.equal(root.dataset.theme, mode);
    assert.equal(meta.content, mode);
    assert.equal(store.getSnapshot(), mode);
  });
}

test('restore legacy settings and prime the next opening', async () => {
  const {root, store, stored, cache} = openPopup('invalid');
  assert.equal(store.getSnapshot(), 'system');
  stored.resolve({[key]: 'dark'});
  await stored.promise;
  assert.equal(root.dataset.theme, 'dark');
  assert.equal(cache.get(key), 'dark');
});

test('a late restore cannot undo choosing system', async () => {
  const {store, stored, cache, writes, meta} = openPopup('dark');
  await store.setPreference('system');
  stored.resolve({[key]: 'dark'});
  await stored.promise;
  assert.equal(store.getSnapshot(), 'system');
  assert.equal(meta.content, 'light dark');
  assert.equal(cache.has(key), false);
  assert.deepEqual(writes, ['system']);
});

test('open panels follow settings changed or cleared in another window', () => {
  const {store, onChange, cache} = openPopup('light');
  const snapshots = [];
  const unsubscribe = store.subscribe(() => snapshots.push(store.getSnapshot()));
  onChange({unrelated: {newValue: 1}}, 'local');
  onChange({[key]: {newValue: 'dark'}}, 'local');
  onChange({[key]: {oldValue: 'dark'}}, 'local');
  unsubscribe();
  onChange({[key]: {newValue: 'light'}}, 'local');
  assert.deepEqual(snapshots, ['dark', 'system']);
  assert.equal(cache.get(key), 'light');
});
