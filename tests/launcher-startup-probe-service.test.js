'use strict';

var assert = require('assert');
var core = require('../tools/launcher-startup-probe/service/service-core');

assert.strictEqual(core.SERVICE_ID, 'hu.szabi.launcher.startupprobe.service');
assert.strictEqual(
  core.managerUri({}),
  'luna://com.webos.service.activitymanager'
);
assert.strictEqual(
  core.managerUri({manager: 'palm'}),
  'luna://com.palm.activitymanager'
);
assert.throws(function () {
  core.managerUri({manager: 'anything-else'});
}, /unsupported Activity Manager endpoint/);

var request = core.immediateCreateRequest();
assert.strictEqual(request.start, true);
assert.strictEqual(request.replace, true);
assert.strictEqual(request.subscribe, false);
assert.deepStrictEqual(request.activity.type, {foreground: true});
assert.strictEqual(request.activity.callback.method,
  'luna://hu.szabi.launcher.startupprobe.service/probe');
assert.deepStrictEqual(request.activity.callback.params, {kind: 'immediate'});
assert.strictEqual(request.activity.type.persist, undefined);
assert.strictEqual(request.activity.type.continuous, undefined);
assert.strictEqual(request.activity.requirements, undefined);
assert.strictEqual(request.activity.trigger, undefined);
var bootup = core.bootupCreateRequest();
assert.strictEqual(bootup.start, true);
assert.strictEqual(bootup.replace, true);
assert.strictEqual(bootup.activity.type.persist, true);
assert.strictEqual(bootup.activity.type.continuous, true);
assert.deepStrictEqual(bootup.activity.requirements, {bootup: true});
assert.deepStrictEqual(bootup.activity.callback.params, {kind: 'bootup'});
assert.strictEqual(core.normalizeKind('immediate'), 'immediate');
assert.strictEqual(core.normalizeKind('bootup'), 'bootup');
assert.strictEqual(core.positiveActivityId(12), 12);
assert.strictEqual(core.positiveActivityId('12'), 12);
assert.strictEqual(core.positiveActivityId(0), null);
assert.strictEqual(core.positiveActivityId(1.5), null);

var safe = core.publicResult({
  returnValue: false,
  activityId: 42,
  errorCode: 13,
  errorText: 'Permission denied',
  secretInternalValue: 'must not leak'
});
assert.deepStrictEqual(safe, {
  returnValue: false,
  activityId: 42,
  errorCode: 13,
  errorText: 'Permission denied'
});

console.log('launcher startup Activity Manager service core tests: PASS');
