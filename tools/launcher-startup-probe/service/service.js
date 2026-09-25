'use strict';

var fs = require('fs');
var Service = require('webos-service');
var core = require('./service-core');

var service = new Service(core.SERVICE_ID);

function readState() {
  try {
    return JSON.parse(fs.readFileSync(core.STATE_PATH, 'utf8'));
  } catch (ignore) {
    return {};
  }
}

function writeState(state) {
  var temporary = core.STATE_PATH + '.new.' + process.pid;
  fs.writeFileSync(temporary, JSON.stringify(state) + '\n', {
    encoding: 'utf8',
    mode: 384
  });
  fs.renameSync(temporary, core.STATE_PATH);
}

function bootUptimeSeconds() {
  try {
    return Number(String(fs.readFileSync('/proc/uptime', 'utf8')).split(/\s+/)[0]);
  } catch (ignore) {
    return null;
  }
}

function failure(message, code, text) {
  message.respond({
    returnValue: false,
    errorCode: code,
    errorText: text
  });
}

service.register('probe', function (message) {
  var kind = core.normalizeKind(message.payload && message.payload.kind);
  if (!kind) {
    failure(message, 22, 'unsupported probe kind');
    return;
  }

  var state = readState();
  state.lastProbe = {
    kind: kind,
    epochMs: Date.now(),
    bootUptimeSeconds: bootUptimeSeconds()
  };
  writeState(state);
  message.respond({
    returnValue: true,
    kind: kind,
    epochMs: state.lastProbe.epochMs,
    bootUptimeSeconds: state.lastProbe.bootUptimeSeconds
  });
});

service.register('status', function (message) {
  message.respond({
    returnValue: true,
    state: readState()
  });
});

service.register('armImmediate', function (message) {
  var manager;
  try {
    manager = core.managerUri(message.payload);
  } catch (error) {
    failure(message, 22, error.message);
    return;
  }

  service.call(manager + '/create', core.immediateCreateRequest(), function (response) {
    var result = core.publicResult(response && response.payload);
    var state = readState();
    state.lastArm = {
      epochMs: Date.now(),
      manager: manager,
      returnValue: result.returnValue,
      activityId: result.activityId || null,
      errorCode: result.errorCode === undefined ? null : result.errorCode
    };
    writeState(state);
    message.respond(result);
  });
});

service.register('cancel', function (message) {
  var state = readState();
  var payload = message.payload || {};
  var activityId = core.positiveActivityId(payload.activityId);
  if (activityId === null && state.lastArm) {
    activityId = core.positiveActivityId(state.lastArm.activityId);
  }
  if (activityId === null) {
    failure(message, 22, 'activityId is required');
    return;
  }

  var manager;
  try {
    manager = core.managerUri(payload);
  } catch (error) {
    failure(message, 22, error.message);
    return;
  }

  service.call(manager + '/cancel', {activityId: activityId}, function (response) {
    var result = core.publicResult(response && response.payload);
    state = readState();
    state.lastCancel = {
      epochMs: Date.now(),
      manager: manager,
      activityId: activityId,
      returnValue: result.returnValue,
      errorCode: result.errorCode === undefined ? null : result.errorCode
    };
    writeState(state);
    message.respond(result);
  });
});
