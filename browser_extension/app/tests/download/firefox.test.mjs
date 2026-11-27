import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';

const {outputFiles} = await build({
  entryPoints: [fileURLToPath(new URL('../../src/background.ts', import.meta.url))],
  bundle: true, write: false, format: 'iife', plugins: [{name: 'desktop', setup(build) {
    build.onResolve({filter: /\/desktop-bridge$/}, () => ({path: 'desktop', namespace: 'fixture'}));
    build.onResolve({filter: /\/icon-progress$/}, () => ({path: 'icons', namespace: 'fixture'}));
    build.onLoad({filter: /.*/, namespace: 'fixture'}, ({path}) => ({contents: path === 'desktop'
      ? 'export const createDesktopBridge = () => globalThis.desktop'
      : 'export const loadBaseIcons = () => {}; export const updateIconForTasks = () => {}'}));
  }}],
});

function start({connected = true, reply = async () => ({ok: true}), settings = {}, isFirefox = true} = {}) {
  const tasks = [];
  const cancelled = [];
  const noop = () => {};
  const event = () => ({addListener(listener, filter, extra) { Object.assign(this, {listener, filter, extra}); }});
  const area = {get: async defaults => ({...defaults, ...settings}), set: async values => Object.assign(settings, values)};
  const chrome = {
    alarms: {onAlarm: event()}, contextMenus: {onClicked: event()}, i18n: {getMessage: key => key},
    runtime: {getManifest: () => ({version: '1'}), getURL: () => isFirefox ? 'moz-extension://test/' : 'chrome-extension://test/', onInstalled: event(), onSuspend: event(), onMessage: event(), onConnect: event()},
    downloads: {onCreated: event(), onDeterminingFilename: isFirefox ? undefined : event(),
      cancel(id, done) { cancelled.push(id); done(); }, erase(_query, done) { done(); }}, tabs: {onActivated: event(), onRemoved: event(), query: async () => []},
    windows: {onFocusChanged: event()}, webNavigation: {onCommitted: event(), onCompleted: event()},
    webRequest: {onCompleted: event(), onErrorOccurred: event(), onSendHeaders: event(), onHeadersReceived: event(), onResponseStarted: event()},
    storage: {local: area, session: area, onChanged: event()},
  };
  const desktop = {isReady: () => connected, setInstallType: noop, loadPersistentState: noop,
    connect: noop, setupReconnectAlarm: noop, sendRequest(task) { tasks.push(task); return reply(); }};
  vm.runInNewContext(outputFiles[0].text, {chrome, browser: chrome, desktop, URL, self: {setTimeout}});
  return {chrome, tasks, cancelled};
}

const url = 'https://files.example/export';
const response = {url, requestId: 'request', type: 'main_frame', method: 'GET', tabId: 1, statusCode: 200,
  originUrl: 'https://page.example/', responseHeaders: [
    {name: 'Content-Disposition', value: 'attachment; filename="report.pdf"'},
    {name: 'Content-Length', value: '1024'},
  ]};

test('Firefox intercepts the response before a download item exists, only after desktop acceptance', async () => {
  let accept;
  const {chrome, tasks} = start({reply: () => new Promise(resolve => { accept = resolve; })});
  const {listener, filter, extra} = chrome.webRequest.onHeadersReceived;
  assert.equal(typeof listener, 'function', 'Firefox needs a response-stage listener');
  assert.ok(extra.includes('blocking') && extra.includes('responseHeaders'));
  assert.ok(filter.types.includes('main_frame') && filter.types.includes('sub_frame'));
  chrome.webRequest.onSendHeaders.listener({requestId: 'unrelated', requestHeaders: [{name: 'Cookie', value: 'other'}]});
  chrome.webRequest.onSendHeaders.listener({requestId: 'request', requestHeaders: [
    {name: 'Cookie', value: 'session=original'}, {name: 'Range', value: 'bytes=0-'},
  ]});
  let settled = false;
  const decision = listener(response).then(result => { settled = true; return result; });
  await new Promise(setImmediate);
  assert.equal(settled, false);
  assert.equal(tasks.length, 1);
  assert.equal(tasks[0].payload.url, url);
  assert.equal(tasks[0].payload.filename, 'report.pdf');
  assert.equal(tasks[0].payload.size, 1024);
  assert.equal(tasks[0].payload.headers.cookie, 'session=original');
  assert.equal(tasks[0].payload.headers.range, undefined);
  accept({ok: true});
  assert.equal((await decision).cancel, true);
});

for (const [name, options, changes, expectedTasks = 0] of [
  ['bypass', {settings: {bypassTs: Date.now()}}],
  ['takeover disabled', {settings: {shouldTakeDownloads: false}}],
  ['excluded extension', {settings: {skipExtensions: '.PDF'}}],
  ['excluded page domain', {settings: {skipDomains: ['page.example']}}],
  ['below minimum size', {settings: {minTakeSizeKB: 2}}],
  ['unknown size', {settings: {minTakeSizeKB: 1, shouldTakeUnknownSize: false}}, {responseHeaders: response.responseHeaders.slice(0, 1)}],
  ['POST', {}, {method: 'POST'}], ['redirect', {}, {statusCode: 302}],
  ['renderable document', {}, {responseHeaders: [{name: 'Content-Type', value: 'text/html'}]}],
  ['desktop rejection', {reply: async () => ({ok: false})}, {}, 1],
  ['disconnect during handoff', {reply: async () => { throw Error('disconnected'); }}, {}, 1],
]) {
  test(`Firefox leaves the native download alone: ${name}`, async () => {
    const {chrome, tasks} = start(options);
    const result = await chrome.webRequest.onHeadersReceived.listener({...response, ...changes});
    assert.notEqual(result?.cancel, true);
    assert.equal(tasks.length, expectedTasks);
  });
}

test('Firefox hands off to the offline queue before cancelling', async () => {
  const settings = {};
  const {chrome} = start({connected: false, settings});
  assert.equal((await chrome.webRequest.onHeadersReceived.listener(response)).cancel, true);
  assert.equal(settings.pendingTasks.length, 1);
  assert.equal(settings.pendingTasks[0].payload.url, url);
});

for (const isFirefox of [true, false]) {
  test(`${isFirefox ? 'Firefox fallback' : 'Chromium'} leaves a rejected download in the browser`, async () => {
    const {chrome, cancelled, tasks} = start({isFirefox, reply: async () => ({ok: false})});
    const item = {id: 7, url, filename: 'report.pdf', referrer: ''};
    let suggestions = 0;
    if (isFirefox) {
      chrome.downloads.onCreated.listener(item);
    } else {
      assert.equal(chrome.webRequest.onHeadersReceived.listener, undefined);
      chrome.downloads.onDeterminingFilename.listener(item, () => { suggestions++; });
    }
    await new Promise(setImmediate);
    assert.equal(tasks.length, 1);
    assert.equal(suggestions, isFirefox ? 0 : 1);
    assert.deepEqual(cancelled, []);
  });
}
