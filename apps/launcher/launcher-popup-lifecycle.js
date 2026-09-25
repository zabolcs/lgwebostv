(function (global) {
  'use strict';

  function create(options) {
    options = options || {};
    var system = options.system || global.PalmSystem;
    var document = options.document || global.document;
    var schedule = options.setTimeout || function (callback, delay) { return global.setTimeout(callback, delay); };
    var unschedule = options.clearTimeout || function (timer) { global.clearTimeout(timer); };
    var generation = 0;
    var pending = null;

    function removeWatch(attempt) {
      if (attempt.timer !== null) {
        unschedule(attempt.timer);
        attempt.timer = null;
      }
      if (attempt.listening) {
        document.removeEventListener('visibilitychange', attempt.listener);
        attempt.listening = false;
      }
    }

    function cancel() {
      generation += 1;
      var attempt = pending;
      pending = null;
      if (attempt) removeWatch(attempt);
    }

    function hide(callbacks) {
      callbacks = callbacks || {};
      cancel();
      var attempt = { generation: generation, timer: null, listening: false, hidden: false };
      pending = attempt;

      function current() {
        return pending === attempt && generation === attempt.generation;
      }

      function finish(hidden, error) {
        if (!current()) return;
        pending = null;
        attempt.hidden = hidden;
        removeWatch(attempt);
        var callback = hidden ? callbacks.onHidden : callbacks.onFailure;
        if (typeof callback === 'function') callback(error);
      }

      attempt.listener = function () {
        if (current() && document.hidden === true) finish(true);
      };

      if (!system || typeof system.keepAlive !== 'function' || typeof system.hide !== 'function' ||
          !document || typeof document.addEventListener !== 'function' || typeof document.removeEventListener !== 'function') {
        finish(false, new Error('Native popup hide API is unavailable.'));
        return false;
      }

      try {
        document.addEventListener('visibilitychange', attempt.listener);
        attempt.listening = true;
        if (typeof callbacks.beforeHide === 'function') callbacks.beforeHide();
        if (!current()) return attempt.hidden;
        system.keepAlive(true);
        if (!current()) return attempt.hidden;
        system.hide();
        if (!current()) return attempt.hidden;
        if (document.hidden === true) finish(true);
        else attempt.timer = schedule(function () {
          if (!current()) return;
          if (document.hidden === true) finish(true);
          else finish(false, new Error('Popup stayed visible after native hide.'));
        }, 450);
      } catch (error) {
        finish(false, error);
      }
      return current() || attempt.hidden;
    }

    // Call cancel on resume before activating the window: a frozen renderer may
    // still have an old deadline queued even after clearTimeout has run.
    return { hide: hide, cancel: cancel };
  }

  global.LauncherPopupLifecycle = { create: create };
}(typeof window !== 'undefined' ? window : this));
