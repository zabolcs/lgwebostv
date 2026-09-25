(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }
  var start = el('tv-pairing-start');
  if (!start) return;
  var refreshButton = el('tv-pairing-refresh');
  var cancel = el('tv-pairing-cancel');
  var status = el('tv-pairing-status');
  var earlyStatus = el('tv-early-launcher-status');
  var approval = el('tv-pairing-approval');
  var approve = el('tv-pairing-approve');
  var screen = el('tv-pairing-screen');
  var screenStatus = el('tv-pairing-screen-status');
  var screenRefresh = el('tv-pairing-screen-refresh');
  var live = null, busy = false, reading = false, revision = 0, pollTimer = null;
  var screenSession = '', screenLoaded = false, screenLoading = false, screenAt = 0;

  function pending() {
    return !!live && ['connecting', 'waiting', 'approving'].indexOf(live.state) !== -1;
  }

  function waiting() { return !!live && live.state === 'waiting' && !!live.id; }

  function api(body) {
    var controller = new AbortController();
    var timeout = window.setTimeout(function () { controller.abort(); }, 30000);
    var options = { method: body ? 'POST' : 'GET', cache: 'no-store', signal: controller.signal };
    if (body) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    return fetch('/api/tv/pairing', options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok || !data.pairing) {
          throw new Error(data.error || 'A párosítás állapota nem érhető el.');
        }
        return data;
      });
    }).finally(function () { window.clearTimeout(timeout); });
  }

  function stopPoll() {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function schedule() {
    stopPoll();
    if (pending() && !document.hidden) pollTimer = window.setTimeout(refresh, 1000);
  }

  function updateButtons() {
    if (screenLoaded && Date.now() - screenAt > 30000) {
      screenLoaded = false;
      screenStatus.textContent = 'A kép már több mint 30 másodperces. Jóváhagyás előtt frissítsd a TV-képet.';
    }
    start.disabled = busy || pending();
    refreshButton.disabled = busy || reading;
    cancel.hidden = !pending();
    cancel.disabled = busy || !live || !live.id;
    approve.disabled = busy || !waiting() || !live.canApprove || !screenLoaded || screenSession !== live.id;
    screenRefresh.disabled = busy || screenLoading || !waiting();
  }

  function resetScreen() {
    screenSession = '';
    screenLoaded = false;
    screenLoading = false;
    screenAt = 0;
    screen.onload = null;
    screen.onerror = null;
    screen.removeAttribute('src');
    screen.hidden = true;
    screenStatus.textContent = '';
  }

  function loadScreen() {
    if (!waiting() || screenLoading || document.hidden) return;
    var id = live.id;
    screenSession = id;
    screenLoaded = false;
    screenLoading = true;
    screenAt = Date.now();
    screen.hidden = true;
    screenStatus.textContent = 'TV-kép lekérése…';
    updateButtons();
    screen.onload = function () {
      if (!waiting() || live.id !== id) return;
      screenLoaded = true;
      screenLoading = false;
      screen.hidden = false;
      screenStatus.textContent = 'TV-kép · ' + new Date().toLocaleTimeString('hu-HU') +
        (live.canApprove ? ' · Jóváhagyás előtt ellenőrizd a kijelölt gombot.' : ' · A jóváhagyás jelenleg csak a TV-n lehetséges.');
      updateButtons();
    };
    screen.onerror = function () {
      if (!waiting() || live.id !== id) return;
      screenLoaded = false;
      screenLoading = false;
      screenStatus.textContent = 'A TV-kép nem érhető el. Frissítsd a képet, vagy hagyd jóvá a kérést a TV-n.';
      updateButtons();
    };
    screen.src = '/api/tv-screen?_=' + Date.now();
  }

  function remaining(deadline) {
    if (!deadline) return '';
    var value = typeof deadline === 'number' ? (deadline < 100000000000 ? deadline * 1000 : deadline) : Date.parse(deadline);
    var seconds = Math.ceil((value - Date.now()) / 1000);
    return Number.isFinite(seconds) && seconds > 0 ? ' Hátralévő idő: ' + seconds + ' mp.' : '';
  }

  function render(data) {
    live = data.pairing;
    var labels = {
      connecting: 'Kapcsolódás a TV-hez; párosítási kérés indítása…',
      waiting: 'A TV jóváhagyására várunk. A távirányítón vagy az alábbi ellenőrzött TV-képnél engedélyezheted.',
      approving: 'Jóváhagyás elküldve; várakozás a TV visszaigazolására…',
      paired: 'A TV párosítva van. A párosítási kulcs a NAS-on van elmentve.',
      success: 'A párosítás sikerült; az új kulcs elmentve a NAS-on.',
      cancelled: 'Párosítás megszakítva.',
      expired: 'A párosítási kérés ideje lejárt. Újraindíthatod a párosítást.',
      failed: 'A párosítás nem sikerült.',
      error: 'A párosítás nem sikerült.'
    };
    var text = labels[live.state] || (live.paired ? labels.paired : 'Még nincs mentett párosítás.');
    if (pending()) text += remaining(live.deadline);
    if (live.error) text += ' ' + live.error;
    if (live.paired && ['cancelled', 'expired', 'failed', 'error'].indexOf(live.state) !== -1) {
      text += ' A korábban mentett párosítás megmaradt.';
    }
    status.textContent = text;
    status.classList.toggle('error', !!live.error || ['expired', 'failed', 'error'].indexOf(live.state) !== -1);
    var early = data.earlyLauncher;
    earlyStatus.hidden = !early;
    if (early) {
      var updated = Number(early.updatedAt) * 1000;
      var fresh = updated > 0 && Date.now() - updated >= 0 && Date.now() - updated < 30000;
      var needsPairing = ['pairing-required', 'host-changed-repair-required'].indexOf(early.event) !== -1;
      earlyStatus.textContent = early.event === 'not-started' ? 'A NAS-os korai launcher-indítás még nincs elindítva.' :
        needsPairing ? 'A NAS-os korai launcher-indításhoz újrapárosítás szükséges.' :
        !fresh ? 'A NAS-os korai launcher-indításról nincs friss állapotjelzés. Az állapot jelenleg nem igazolható.' :
        early.observeOnly ? 'A NAS-os korai launcher-indítás megfigyelési módban van: nem indít alkalmazást.' :
        early.connected ? 'A NAS-os korai launcher-indító kapcsolódik a TV-hez és figyeli az indítás feltételeit.' :
        'A NAS-os korai launcher-indító várakozik a TV natív hálózati kapcsolatára.';
    }
    approval.hidden = !waiting();
    if (!waiting()) resetScreen();
    else if (screenSession !== live.id) { resetScreen(); loadScreen(); }
    updateButtons();
  }

  function showError(error) {
    screenLoaded = false;
    status.textContent = 'Nem igazolt állapot: ' + (error.name === 'AbortError' ? 'A kérés időtúllépés miatt megszakadt.' : error.message) +
      ' A korábban mentett párosítás nem törlődik. Az állapot újra lekérhető.';
    status.classList.add('error');
  }

  function refresh() {
    stopPoll();
    if (busy || reading) return;
    reading = true;
    var current = revision;
    updateButtons();
    api().then(function (data) { if (current === revision) render(data); })
      .catch(function (error) { if (current === revision) showError(error); })
      .finally(function () { reading = false; updateButtons(); schedule(); });
  }

  function change(action) {
    if (busy) return;
    if (action === 'start' && pending()) return;
    if (action !== 'start' && (!live || !live.id)) return;
    if (action === 'approve' && (approve.disabled || !waiting())) return;
    var body = { action: action };
    if (action !== 'start') body.id = live.id;
    busy = true;
    revision++;
    stopPoll();
    updateButtons();
    status.classList.remove('error');
    status.textContent = action === 'start' ? 'Párosítás indítása…' : action === 'approve' ? 'Jóváhagyás küldése…' : 'Párosítás megszakítása…';
    api(body).then(render).catch(showError).finally(function () {
      busy = false;
      updateButtons();
      // The command may have reached the NAS even if its response was lost.
      refresh();
    });
  }

  start.addEventListener('click', function () { change('start'); });
  cancel.addEventListener('click', function () { change('cancel'); });
  approve.addEventListener('click', function () { change('approve'); });
  refreshButton.addEventListener('click', refresh);
  screenRefresh.addEventListener('click', loadScreen);
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stopPoll();
    else { if (waiting() && Date.now() - screenAt > 30000) loadScreen(); refresh(); }
  });
  refresh();
}());
