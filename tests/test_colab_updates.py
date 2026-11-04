"""Offline frontend timer lifecycle; no browser, auth or remote requests."""
import shutil
import subprocess
import unittest

from libya_landcover.colab_updates import refresh_script


@unittest.skipUnless(shutil.which('node'), 'Node is needed for the JavaScript lifecycle check')
class ColabTimerTests(unittest.TestCase):
    def test_serial_calls_retirement_and_transport_failures(self):
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = require('node:fs').readFileSync(0, 'utf8');
(async () => {
  const timers = new Map(); let id = 0, resolve, reject, calls = 0, onExit;
  const context = vm.createContext({
    setTimeout(fn, delay) { timers.set(++id, {fn, delay}); return id; },
    clearTimeout(key) { timers.delete(key); },
    window: { addEventListener(event, fn) { assert.equal(event, 'pagehide'); onExit = fn; } },
    google: {colab: {kernel: {invokeFunction(name, args, kwargs) {
      assert.equal(name, 'test-refresh');
      assert.equal(args.length, 0); assert.equal(Object.keys(kwargs).length, 0);
      calls++; return new Promise((ok, fail) => { resolve = ok; reject = fail; });
    }}}}
  });
  function next() {
    assert.equal(timers.size, 1);
    const [key, item] = [...timers][0]; timers.delete(key);
    return item.fn();
  }
  vm.runInContext(source, context);
  let pending = next();
  assert.equal(calls, 1); assert.equal(timers.size, 0); // no overlapping callbacks
  resolve({data: {'application/json': {closed: false}}}); await pending;
  assert.equal([...timers.values()][0].delay, 5000);
  pending = next(); resolve({data: {'application/json': {closed: true}}}); await pending;
  assert.equal(timers.size, 0);

  vm.runInContext(source, context);
  const oldTick = [...timers.values()][0].fn;
  vm.runInContext(source, context); // replacement clears the prior timer
  assert.equal(timers.size, 1);
  const previousCalls = calls; await oldTick(); assert.equal(calls, previousCalls);
  for (let n = 0; n < 3; n++) {
    pending = next(); reject(new Error('Disconnected')); await pending;
    assert.equal(timers.size, n < 2 ? 1 : 0);
  }
  vm.runInContext(source, context); onExit(); assert.equal(timers.size, 0);
  console.log('serial requests, closed callbacks, replacement, transport failure and page exit passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run(['node', '-e', harness], input=refresh_script('test-refresh'),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
