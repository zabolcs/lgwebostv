'use strict';

var SERVICE_ID = 'hu.szabi.launcher.startupprobe.service';
var STATE_PATH = '/tmp/hu.szabi.launcher.startupprobe.activity.json';
var MANAGERS = {
  webos: 'luna://com.webos.service.activitymanager',
  palm: 'luna://com.palm.activitymanager'
};

function managerUri(payload) {
  var name = payload && payload.manager !== undefined ? String(payload.manager) : 'webos';
  if (!Object.prototype.hasOwnProperty.call(MANAGERS, name)) {
    throw new Error('unsupported Activity Manager endpoint');
  }
  return MANAGERS[name];
}

function immediateCreateRequest() {
  return {
    activity: {
      name: SERVICE_ID + '.immediate',
      description: 'One-shot no-reboot launcher startup callback probe',
      type: {
        foreground: true
      },
      callback: {
        method: 'luna://' + SERVICE_ID + '/probe',
        params: {
          kind: 'immediate'
        }
      }
    },
    replace: true,
    start: true,
    subscribe: false
  };
}

function bootupCreateRequest() {
  return {
    activity: {
      name: SERVICE_ID + '.bootup',
      description: 'Persistent launcher bootup callback timing probe',
      type: {persist: true, continuous: true},
      requirements: {bootup: true},
      callback: {method: 'luna://' + SERVICE_ID + '/probe', params: {kind: 'bootup'}}
    },
    replace: true,
    start: true,
    subscribe: false
  };
}

function firstAppLaunchedCreateRequest() {
  return {
    activity: {
      name: SERVICE_ID + '.firstAppLaunched',
      description: 'Persistent first-app-launched callback timing probe',
      type: {foreground: true, persist: true, continuous: true},
      trigger: {
        method: 'luna://com.webos.bootManager/getBootStatus',
        params: {subscribe: true},
        where: {prop: 'firstAppLaunched', op: '=', val: true}
      },
      callback: {
        method: 'luna://' + SERVICE_ID + '/probe',
        params: {kind: 'firstAppLaunched'}
      }
    },
    replace: true,
    start: true,
    subscribe: false
  };
}

function normalizeKind(value) {
  return value === 'immediate' || value === 'bootup' || value === 'firstAppLaunched' ? value : null;
}

function positiveActivityId(value) {
  var number = Number(value);
  if (!isFinite(number) || number <= 0 || Math.floor(number) !== number) {
    return null;
  }
  return number;
}

function publicResult(payload) {
  payload = payload && typeof payload === 'object' ? payload : {};
  var result = {
    returnValue: payload.returnValue === true
  };
  if (positiveActivityId(payload.activityId) !== null) {
    result.activityId = positiveActivityId(payload.activityId);
  }
  if (payload.errorCode !== undefined) {
    result.errorCode = payload.errorCode;
  }
  if (payload.errorText !== undefined) {
    result.errorText = String(payload.errorText).slice(0, 240);
  }
  return result;
}

module.exports = {
  SERVICE_ID: SERVICE_ID,
  STATE_PATH: STATE_PATH,
  managerUri: managerUri,
  immediateCreateRequest: immediateCreateRequest,
  bootupCreateRequest: bootupCreateRequest,
  firstAppLaunchedCreateRequest: firstAppLaunchedCreateRequest,
  normalizeKind: normalizeKind,
  positiveActivityId: positiveActivityId,
  publicResult: publicResult
};
