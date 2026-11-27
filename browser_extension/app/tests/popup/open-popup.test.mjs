import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';

const {outputFiles} = await build({
  entryPoints: [fileURLToPath(new URL('../../src/background/chrome-helpers.ts', import.meta.url))],
  bundle: true, write: false, format: 'iife', globalName: 'helpers',
});

async function open({error, result = {ok: true}, enabled = true, existing = []}) {
  const opened = [];
  const focused = [];
  const chrome = {
    i18n: {getMessage: key => key},
    action: {openPopup: async () => { if (error) { throw Error(error); } }},
    storage: {local: {get: async () => ({shouldOpenPopupOnSent: enabled})}},
    runtime: {getURL: path => `moz-extension://test/${path.replace(/^\//, '')}`, getManifest: () => ({action: {default_popup: 'popup.html'}})},
    tabs: {query: async () => existing},
    windows: {getLastFocused: async () => ({focused: true, incognito: false}), create: async options => opened.push(options), update: async id => focused.push(id)},
  };
  const ctx = vm.createContext({chrome});
  vm.runInContext(outputFiles[0].text, ctx);
  await ctx.helpers.openActionPopup(result);
  return {opened, focused};
}

const gestureError = 'openPopup requires a user gesture';

test('Firefox opens the extension panel when its toolbar requires a gesture', async () => {
  const {opened} = await open({error: gestureError});
  assert.equal(opened[0]?.type, 'popup');
  assert.equal(opened[0].url, 'moz-extension://test/popup.html');
  const {focused} = await open({error: gestureError, existing: [{windowId: 5, incognito: false}]});
  assert.deepEqual(focused, [5]);
});

test('no fallback on success, focus errors, draft tasks or disabled popups', async () => {
  for (const options of [{}, {error: 'window is not focused'}, {result: {ok: true, isDrafted: true}, error: gestureError}, {enabled: false, error: gestureError}]) {
    assert.deepEqual(await open(options), {opened: [], focused: []});
  }
});
