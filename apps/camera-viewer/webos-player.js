(function () {
  'use strict';

  var CHANNEL = 'hu.szabi.cameraviewer.player';
  var SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$/;
  var SESSION_ID = /^[0-9a-f]{32}$/;
  var params = new URLSearchParams(window.location.hash.slice(1));
  var source = params.get('src') || '';
  var session = (params.get('session') || '').toLowerCase();
  var audioRequested = params.get('audio') === '1';
  var video = document.getElementById('video');
  var pc = null;
  var ws = null;
  var remoteStream = null;
  var stopped = false;
  var reportedError = false;
  var startupTimer = null;
  var playRetryTimer = null;

  function notify(type, detail) {
    try {
      window.parent.postMessage({
        channel: CHANNEL,
        type: type,
        session: session,
        detail: detail || ''
      }, '*');
    } catch (error) { /* parent timeout provides the fallback */ }
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    if (startupTimer) window.clearTimeout(startupTimer);
    if (playRetryTimer) window.clearTimeout(playRetryTimer);
    startupTimer = null;
    playRetryTimer = null;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try { ws.close(); } catch (error) { /* no-op */ }
      ws = null;
    }
    if (pc) {
      pc.ontrack = null;
      pc.onicecandidate = null;
      pc.onconnectionstatechange = null;
      pc.oniceconnectionstatechange = null;
      try { pc.close(); } catch (error) { /* no-op */ }
      pc = null;
    }
    if (remoteStream && remoteStream.getTracks) {
      var tracks = remoteStream.getTracks();
      for (var i = 0; i < tracks.length; i += 1) {
        try { tracks[i].stop(); } catch (error) { /* no-op */ }
      }
    }
    remoteStream = null;
    try { video.pause(); } catch (error) { /* no-op */ }
    video.srcObject = null;
    video.removeAttribute('src');
  }

  function fail(message) {
    if (stopped || reportedError) return;
    reportedError = true;
    notify('error', message);
    stop();
  }

  function send(type, value) {
    if (!ws || ws.readyState !== WebSocket.OPEN || stopped) return;
    ws.send(JSON.stringify({ type: type, value: value }));
  }

  function tryPlay() {
    if (stopped || !video.srcObject) return;
    var playResult;
    try { playResult = video.play(); } catch (error) { playResult = null; }
    if (playResult && typeof playResult.catch === 'function') {
      playResult.catch(function () {
        if (stopped) return;
        // webOS may reject the first play() while the remote stream is still
        // gaining tracks. Retry muted; the startup timeout remains the final
        // failure boundary instead of immediately dropping to MJPEG.
        video.muted = true;
        notify('muted', 'autoplay');
        if (playRetryTimer) window.clearTimeout(playRetryTimer);
        playRetryTimer = window.setTimeout(tryPlay, 250);
      });
    }
  }

  function attachTrack(event) {
    if (stopped) return;
    if (event.streams && event.streams[0]) {
      remoteStream = event.streams[0];
    } else {
      if (!remoteStream) remoteStream = new MediaStream();
      remoteStream.addTrack(event.track);
    }
    video.srcObject = remoteStream;
    tryPlay();
  }

  function addRemoteCandidate(value) {
    if (!pc || value === undefined || value === null) return;
    var candidate = typeof value === 'string' ? { candidate: value, sdpMid: '0' } : value;
    try {
      var result = pc.addIceCandidate(candidate);
      if (result && typeof result.catch === 'function') result.catch(function () {});
    } catch (error) { /* a later candidate may still succeed */ }
  }

  function answerOffer(sdp) {
    pc.setRemoteDescription({ type: 'offer', sdp: sdp })
      .then(function () { return pc.createAnswer(); })
      .then(function (answer) { return pc.setLocalDescription(answer); })
      .then(function () { send('webrtc/answer', pc.localDescription.sdp); })
      .catch(function () { fail('offer'); });
  }

  function makeOffer() {
    try {
      pc.addTransceiver('video', { direction: 'recvonly' });
      if (audioRequested) pc.addTransceiver('audio', { direction: 'recvonly' });
    } catch (error) {
      fail('transceiver');
      return;
    }
    pc.createOffer()
      .then(function (offer) {
        return pc.setLocalDescription(offer).then(function () { send('webrtc/offer', offer.sdp); });
      })
      .catch(function () { fail('local-offer'); });
  }

  function start() {
    if (!SAFE_ID.test(source) || !SESSION_ID.test(session)) {
      fail('params');
      return;
    }
    if (!window.RTCPeerConnection || !window.WebSocket || !window.MediaStream) {
      fail('unsupported');
      return;
    }
    pc = new RTCPeerConnection({ iceServers: [] });
    video.autoplay = true;
    video.muted = !audioRequested;
    video.volume = 1;
    pc.ontrack = attachTrack;
    pc.onicecandidate = function (event) {
      send('webrtc/candidate', event.candidate ? event.candidate.candidate : '');
    };
    pc.onconnectionstatechange = function () {
      if (!pc || stopped) return;
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed') fail('peer-' + pc.connectionState);
    };
    pc.oniceconnectionstatechange = function () {
      if (!pc || stopped) return;
      if (pc.iceConnectionState === 'failed') fail('ice-failed');
    };

    var wsScheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    ws = new WebSocket(wsScheme + window.location.host + '/api/ws?src=' + encodeURIComponent(source));
    ws.onopen = function () {
      if (stopped) return;
      notify('ready');
      makeOffer();
    };
    ws.onmessage = function (event) {
      if (stopped || typeof event.data !== 'string') return;
      var message;
      try { message = JSON.parse(event.data); } catch (error) { return; }
      if (message.type === 'webrtc/answer') {
        pc.setRemoteDescription({ type: 'answer', sdp: message.value }).catch(function () { fail('answer'); });
      } else if (message.type === 'webrtc/offer') {
        answerOffer(message.value);
      } else if (message.type === 'webrtc/candidate') {
        addRemoteCandidate(message.value);
      } else if (message.type === 'error') {
        fail('go2rtc');
      }
    };
    ws.onerror = function () { fail('websocket'); };
    ws.onclose = function () { if (!stopped) fail('websocket-closed'); };
    startupTimer = window.setTimeout(function () { fail('timeout'); }, 12000);
  }

  video.addEventListener('playing', function () {
    if (stopped) return;
    if (startupTimer) window.clearTimeout(startupTimer);
    startupTimer = null;
    notify('playing', video.muted ? 'muted' : 'audio');
  });
  video.addEventListener('loadedmetadata', tryPlay);
  video.addEventListener('canplay', tryPlay);
  video.addEventListener('error', function () { fail('video'); });
  window.addEventListener('message', function (event) {
    var data = event.data;
    if (event.source !== window.parent || !data || data.channel !== CHANNEL || data.session !== session) return;
    if (data.type === 'stop') stop();
    else if (data.type === 'set-muted' && audioRequested && !stopped) {
      video.muted = data.muted !== false;
      tryPlay();
      notify('audio-state', video.muted ? 'muted' : 'audio');
    }
  });
  window.addEventListener('pagehide', stop);
  window.addEventListener('beforeunload', stop);
  start();
}());
