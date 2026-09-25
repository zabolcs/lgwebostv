'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var appRoot = path.resolve(__dirname, '..');
var sentToParent = [];
var windowListeners = {};
var videoListeners = {};
var timers = {};
var timerId = 0;

var video = {
  srcObject: null,
  muted: false,
  volume: 0,
  playCount: 0,
  addEventListener: function (name, handler) { videoListeners[name] = handler; },
  play: function () { this.playCount += 1; return Promise.resolve(); },
  pause: function () {},
  removeAttribute: function () {}
};

function FakeStream(tracks) {
  this.tracks = tracks || [];
}
FakeStream.prototype.addTrack = function (track) { this.tracks.push(track); };
FakeStream.prototype.getTracks = function () { return this.tracks.slice(); };

function FakePeerConnection() {
  this.transceivers = [];
  this.localDescription = null;
  this.remoteDescriptions = [];
  this.remoteCandidates = [];
  this.closed = false;
  FakePeerConnection.instance = this;
}
FakePeerConnection.prototype.addTransceiver = function (kind, options) {
  this.transceivers.push({ kind: kind, direction: options.direction });
};
FakePeerConnection.prototype.createOffer = function () { return Promise.resolve({ type: 'offer', sdp: 'test-offer' }); };
FakePeerConnection.prototype.setLocalDescription = function (value) { this.localDescription = value; return Promise.resolve(); };
FakePeerConnection.prototype.setRemoteDescription = function (value) { this.remoteDescriptions.push(value); return Promise.resolve(); };
FakePeerConnection.prototype.createAnswer = function () { return Promise.resolve({ type: 'answer', sdp: 'test-answer' }); };
FakePeerConnection.prototype.addIceCandidate = function (value) { this.remoteCandidates.push(value); return Promise.resolve(); };
FakePeerConnection.prototype.close = function () { this.closed = true; };

function FakeWebSocket(url) {
  this.url = url;
  this.readyState = 0;
  this.messages = [];
  this.closed = false;
  FakeWebSocket.instance = this;
}
FakeWebSocket.OPEN = 1;
FakeWebSocket.prototype.send = function (value) { this.messages.push(JSON.parse(value)); };
FakeWebSocket.prototype.close = function () { this.closed = true; };

var parentWindow = {
  postMessage: function (message) { sentToParent.push(message); }
};
var root = {
  location: {
    protocol: 'http:',
    host: '192.168.0.150:1985',
    hash: '#src=camera_kapu_felso_h264&session=0123456789abcdef0123456789abcdef&audio=1'
  },
  parent: parentWindow,
  RTCPeerConnection: FakePeerConnection,
  WebSocket: FakeWebSocket,
  MediaStream: FakeStream,
  URLSearchParams: URLSearchParams,
  JSON: JSON,
  Promise: Promise,
  encodeURIComponent: encodeURIComponent,
  setTimeout: function (handler) { timerId += 1; timers[timerId] = handler; return timerId; },
  clearTimeout: function (id) { delete timers[id]; },
  addEventListener: function (name, handler) { windowListeners[name] = handler; }
};
root.window = root;
root.document = { getElementById: function (id) { return id === 'video' ? video : null; } };

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

(async function () {
  var source = fs.readFileSync(path.join(appRoot, 'webos-player.js'), 'utf8');
  vm.runInContext(source, vm.createContext(root), { filename: 'webos-player.js' });

  var ws = FakeWebSocket.instance;
  var pc = FakePeerConnection.instance;
  assert.strictEqual(ws.url, 'ws://192.168.0.150:1985/api/ws?src=camera_kapu_felso_h264');

  ws.readyState = FakeWebSocket.OPEN;
  ws.onopen();
  await flushPromises();
  assert.deepStrictEqual(pc.transceivers, [
    { kind: 'video', direction: 'recvonly' },
    { kind: 'audio', direction: 'recvonly' }
  ]);
  assert.strictEqual(ws.messages[0].type, 'webrtc/offer');
  assert.strictEqual(ws.messages[0].value, 'test-offer');
  assert.strictEqual(sentToParent[0].type, 'ready');

  ws.onmessage({ data: JSON.stringify({ type: 'webrtc/answer', value: 'test-answer' }) });
  ws.onmessage({ data: JSON.stringify({ type: 'webrtc/candidate', value: 'candidate:test' }) });
  await flushPromises();
  assert.strictEqual(pc.remoteDescriptions[0].type, 'answer');
  assert.strictEqual(pc.remoteCandidates[0].candidate, 'candidate:test');
  assert.strictEqual(pc.remoteCandidates[0].sdpMid, '0');

  var track = { id: 'track-1', stop: function () {} };
  var stream = new FakeStream([track]);
  pc.ontrack({ track: track, streams: [stream] });
  assert.strictEqual(video.srcObject, stream, 'track event must attach the stream immediately');
  assert.strictEqual(video.playCount, 1);
  assert.strictEqual(video.muted, false);
  videoListeners.playing();
  assert.strictEqual(sentToParent[sentToParent.length - 1].type, 'playing');

  windowListeners.message({
    source: parentWindow,
    data: {
      channel: 'hu.szabi.cameraviewer.player', type: 'set-muted', muted: true,
      session: '0123456789abcdef0123456789abcdef'
    }
  });
  assert.strictEqual(video.muted, true);
  assert.strictEqual(sentToParent[sentToParent.length - 1].type, 'audio-state');

  windowListeners.message({
    source: parentWindow,
    data: {
      channel: 'hu.szabi.cameraviewer.player',
      type: 'stop',
      session: '0123456789abcdef0123456789abcdef'
    }
  });
  assert.strictEqual(ws.closed, true);
  assert.strictEqual(pc.closed, true);
  assert.strictEqual(video.srcObject, null);

  assert.strictEqual(/fail\('autoplay'\)/.test(source), false, 'Az első autoplay hiba nem válthat azonnal MJPEG-re.');
  assert.ok(/setTimeout\(tryPlay, 250\)/.test(source));

  console.log('webos hosted player tests: PASS');
}()).catch(function (error) {
  console.error(error);
  process.exitCode = 1;
});
